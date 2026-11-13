"""Schema creation and migration (SPEC-001 §5, SPEC-007 §2).

Migrations are a chain of numbered files, applied in order, with `schema_meta.schema_version` as the
single source of truth. A v1 database migrates forward by running only the files it has not seen.

Written against a narrow protocol rather than DuckDB so the rules can be tested with any SQL engine,
and so this layer imports no infrastructure type (D-004).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from gtaf.domain.invariants import SUPPORTED_SCHEMA_VERSION

_MIGRATION_NAME_RE = re.compile(r"^(\d{3})_.+\.sql$")


class SqlCursor(Protocol):
    """Minimal result cursor: everything this module needs from a database driver."""

    def fetchall(self) -> list[tuple[object, ...]]:
        """Return all remaining rows."""
        ...

    def fetchone(self) -> tuple[object, ...] | None:
        """Return the next row, or None."""
        ...


class SqlConnection(Protocol):
    """Minimal connection: enough to inspect and create a schema."""

    def execute(self, query: str) -> SqlCursor:
        """Execute one SQL statement and return its cursor."""
        ...


class SchemaVersionError(RuntimeError):
    """Raised when a database's schema version is not one this build can move.

    Attributes:
        found: Version read from the database.
        supported: Highest version this build knows.
    """

    def __init__(self, found: object, supported: str) -> None:
        self.found = found
        self.supported = supported
        super().__init__(
            f"unsupported schema_version {found!r} (this build supports up to {supported!r}). "
            f"Refusing to proceed — migrate the database or use a matching build."
        )


@dataclass(frozen=True, slots=True)
class Migration:
    """One numbered migration file.

    Attributes:
        version: Numeric version taken from the filename, e.g. ``2`` for ``002_topics.sql``.
        name: Filename, for logging.
        sql: File contents.
    """

    version: int
    name: str
    sql: str


@dataclass(frozen=True, slots=True)
class MigrateResult:
    """Outcome of applying migrations.

    Attributes:
        from_version: Version before the call, or None for a fresh database.
        to_version: Version after the call.
        applied: Versions applied, in order (empty when already current).
    """

    from_version: str | None
    to_version: str
    applied: tuple[int, ...]


def parse_migrations(files: Sequence[tuple[str, str]]) -> list[Migration]:
    """Build the migration chain from ``(filename, sql)`` pairs.

    Args:
        files: Filename and contents for every candidate file.

    Returns:
        Migrations sorted by version.

    Raises:
        ValueError: If a filename does not carry a numeric version, or two files share one. Two
            files with the same number would make the applied order ambiguous — that must fail
            loudly rather than silently pick one.
    """
    migrations: list[Migration] = []
    seen: dict[int, str] = {}
    for name, sql in files:
        match = _MIGRATION_NAME_RE.match(name)
        if match is None:
            continue
        version = int(match.group(1))
        if version in seen:
            raise ValueError(
                f"duplicate migration version {version}: {seen[version]!r} and {name!r}"
            )
        seen[version] = name
        migrations.append(Migration(version=version, name=name, sql=sql))
    migrations.sort(key=lambda migration: migration.version)
    return migrations


def split_statements(sql: str) -> list[str]:
    """Split a migration file into executable statements.

    Args:
        sql: File contents.

    Returns:
        Non-empty statements, with surrounding whitespace removed.

    Notes:
        Full-line comments are dropped **before** splitting, because a comment may legitimately
        contain a semicolon or a quote and would otherwise be cut into a fragment that looks like
        SQL. Trailing comments after a statement are not supported; migration files put comments on
        their own lines.
    """
    body = "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))
    return [statement.strip() for statement in body.split(";") if statement.strip()]


def read_schema_version(conn: SqlConnection) -> str | None:
    """Read ``schema_meta.schema_version`` if the table exists.

    Args:
        conn: Open connection.

    Returns:
        The stored version, or None when the table or row is absent (a fresh database).
    """
    tables = conn.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_name = 'schema_meta'"
    ).fetchall()
    if not tables:
        return None
    row = conn.execute("SELECT value FROM schema_meta WHERE key = 'schema_version'").fetchone()
    if row is None:
        return None
    return str(row[0])


def _apply(conn: SqlConnection, migration: Migration) -> None:
    """Execute one migration's statements in order.

    Args:
        conn: Open read-write connection.
        migration: Migration to apply.

    Raises:
        ValueError: If the file contains no statements, which would silently skip a version.
    """
    statements = split_statements(migration.sql)
    if not statements:
        raise ValueError(f"migration {migration.name!r} is empty; refusing to skip a version")
    for statement in statements:
        conn.execute(statement)


def migrate_database(conn: SqlConnection, migrations: Sequence[Migration]) -> MigrateResult:
    """Bring a database up to the newest known schema version.

    Args:
        conn: Read-write connection.
        migrations: The full chain, sorted or not.

    Returns:
        Which versions were applied and the resulting version.

    Raises:
        ValueError: If the chain is empty.
        SchemaVersionError: If the database is newer than this build, or does not reach the expected
            version after applying (a migration that forgot its version marker).
    """
    if not migrations:
        raise ValueError("no migrations found; refusing to operate without a schema")

    chain = sorted(migrations, key=lambda migration: migration.version)
    highest = chain[-1].version
    expected = str(highest)
    if expected != SUPPORTED_SCHEMA_VERSION:
        raise ValueError(
            f"migration chain reaches v{highest} but the code expects "
            f"v{SUPPORTED_SCHEMA_VERSION}; they must agree"
        )

    current = read_schema_version(conn)
    applied: list[int] = []

    if current is not None:
        current_version = int(current)
        if current_version > highest:
            raise SchemaVersionError(current, expected)
        pending = [migration for migration in chain if migration.version > current_version]
    else:
        pending = list(chain)

    for migration in pending:
        _apply(conn, migration)
        applied.append(migration.version)

    version = read_schema_version(conn)
    if version != expected:
        raise SchemaVersionError(version, expected)
    return MigrateResult(
        from_version=current, to_version=version, applied=tuple(applied)
    )
