"""Database initialisation use case (FR-1, FR-2, FR-3).

Written against a narrow protocol rather than DuckDB so the rules can be tested with any SQL
engine, and so this layer imports no infrastructure type (D-004). The composition root in
``gtaf.cli`` supplies the real connection and the migration text.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from gtaf.domain.invariants import SUPPORTED_SCHEMA_VERSION

_MIGRATION_VERSION = SUPPORTED_SCHEMA_VERSION


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
    """Raised when a database's schema version is not the one this code understands.

    Attributes:
        found: Version read from the database.
        supported: Version this build supports.
    """

    def __init__(self, found: object, supported: str) -> None:
        self.found = found
        self.supported = supported
        super().__init__(
            f"unsupported schema_version {found!r} (this build supports {supported!r}). "
            f"Refusing to proceed — migrate the database or use a matching build."
        )


@dataclass(frozen=True, slots=True)
class InitResult:
    """Outcome of ``initialize_database``.

    Attributes:
        applied: True when the migration was executed, False when the database already existed.
        schema_version: Version present after the call.
    """

    applied: bool
    schema_version: str


def split_statements(sql: str) -> list[str]:
    """Split a migration file into executable statements.

    Args:
        sql: File contents.

    Returns:
        Non-empty statements, with surrounding whitespace removed.

    Notes:
        Full-line comments are dropped **before** splitting, because a comment may legitimately
        contain a semicolon or a quote and would otherwise be cut into a fragment that looks
        like SQL — which is exactly the bug that produced "unterminated quoted identifier" the
        first time this ran. Trailing comments after a statement are not supported; migration
        files put comments on their own lines.
    """
    body = "\n".join(
        line for line in sql.splitlines() if not line.lstrip().startswith("--")
    )
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
    row = conn.execute(
        "SELECT value FROM schema_meta WHERE key = 'schema_version'"
    ).fetchone()
    if row is None:
        return None
    return str(row[0])


def initialize_database(conn: SqlConnection, migration_sql: str) -> InitResult:
    """Create the schema at a path, idempotently (FR-1, FR-3).

    Args:
        conn: A read-write connection to the target database.
        migration_sql: Contents of ``001_init.sql``.

    Returns:
        ``InitResult`` describing whether anything was applied.

    Raises:
        SchemaVersionError: If the database already carries a version this build does not
            support (FR-2). Nothing is modified in that case.
    """
    existing = read_schema_version(conn)
    if existing is not None:
        if existing != _MIGRATION_VERSION:
            raise SchemaVersionError(existing, _MIGRATION_VERSION)
        return InitResult(applied=False, schema_version=existing)

    statements = split_statements(migration_sql)
    if not statements:
        raise ValueError("migration file is empty; refusing to create an unversioned database")

    for statement in statements:
        conn.execute(statement)

    version = read_schema_version(conn)
    if version != _MIGRATION_VERSION:
        raise SchemaVersionError(version, _MIGRATION_VERSION)
    return InitResult(applied=True, schema_version=version)
