"""Migration chain tests (SPEC-001 FR-1…FR-3, SPEC-007 §2).

The chain is what makes a schema change safe on a database that already holds data, so these tests
cover fresh creation, forward migration from v1, and refusal of a database newer than the code.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gtaf.application.initialize import (
    SchemaVersionError,
    migrate_database,
    parse_migrations,
    read_schema_version,
    split_statements,
)
from gtaf.domain.invariants import SUPPORTED_SCHEMA_VERSION
from gtaf.infrastructure.db import connect, load_migrations


def test_fresh_database_reaches_supported_version(db_file: Path) -> None:
    """A new path gets the whole chain and ends at the version the code expects."""
    migrations = load_migrations()
    conn = connect(db_file)
    try:
        result = migrate_database(conn, migrations)
        tables = {
            str(row[0])
            for row in conn.execute(
                "SELECT table_name FROM information_schema.tables"
            ).fetchall()
        }
    finally:
        conn.close()

    assert result.from_version is None
    assert result.to_version == SUPPORTED_SCHEMA_VERSION
    assert result.applied == tuple(m.version for m in migrations)
    assert "topics" in tables
    assert "res_topics" in tables


def test_second_run_applies_nothing(db_file: Path) -> None:
    """Idempotence: the chain is not re-applied."""
    migrations = load_migrations()
    conn = connect(db_file)
    try:
        migrate_database(conn, migrations)
        again = migrate_database(conn, migrations)
    finally:
        conn.close()

    assert again.applied == ()
    assert again.to_version == SUPPORTED_SCHEMA_VERSION


def test_v1_database_migrates_forward(db_file: Path) -> None:
    """A database created by the v1 build gains the topic tables, starting from version 1."""
    migrations = load_migrations()
    v1 = next(migration for migration in migrations if migration.version == 1)

    conn = connect(db_file)
    try:
        for statement in split_statements(v1.sql):
            conn.execute(statement)
        assert read_schema_version(conn) == "1"

        result = migrate_database(conn, migrations)
        tables = {
            str(row[0])
            for row in conn.execute(
                "SELECT table_name FROM information_schema.tables"
            ).fetchall()
        }
    finally:
        conn.close()

    assert result.from_version == "1"
    assert result.to_version == SUPPORTED_SCHEMA_VERSION
    assert result.applied == (2,)
    assert "topics" in tables
    assert "res_topics" in tables


def test_newer_database_is_refused(db_file: Path) -> None:
    """A database from a future build must not be silently downgraded."""
    migrations = load_migrations()
    conn = connect(db_file)
    try:
        migrate_database(conn, migrations)
        conn.execute("UPDATE schema_meta SET value = '99' WHERE key = 'schema_version'")
        with pytest.raises(SchemaVersionError):
            migrate_database(conn, migrations)
    finally:
        conn.close()


def test_chain_must_match_the_code_version(tmp_path: Path) -> None:
    """A chain that stops short of the code's version is a build error, not a runtime surprise."""
    migrations = [migration for migration in load_migrations() if migration.version == 1]
    conn = connect(tmp_path / "short.duckdb")
    try:
        with pytest.raises(ValueError, match="must agree"):
            migrate_database(conn, migrations)
    finally:
        conn.close()


def test_empty_chain_is_refused(db_file: Path) -> None:
    """No migrations means no schema; refuse rather than create an unversioned database."""
    conn = connect(db_file)
    try:
        with pytest.raises(ValueError):
            migrate_database(conn, [])
    finally:
        conn.close()


def test_parse_migrations_sorts_and_rejects_duplicates() -> None:
    """Order comes from the filename, and a duplicated number is ambiguous, so it fails."""
    chain = parse_migrations(
        [("002_b.sql", "SELECT 2;"), ("001_a.sql", "SELECT 1;"), ("notes.txt", "ignored")]
    )
    assert [migration.version for migration in chain] == [1, 2]

    with pytest.raises(ValueError, match="duplicate"):
        parse_migrations([("001_a.sql", ""), ("001_b.sql", "")])


def test_split_statements_ignores_semicolons_inside_comments() -> None:
    """Regression: a comment containing a semicolon must not become a fake statement."""
    sql = '-- a comment with a ; and a "quote\nSELECT 1;\n-- another ; comment\nSELECT 2;'
    assert split_statements(sql) == ["SELECT 1", "SELECT 2"]
