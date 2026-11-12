"""Migration and idempotency tests (SPEC-001 §9 cases 1-4, FR-1…FR-3)."""

from __future__ import annotations

from pathlib import Path

import pytest

from gtaf.application.initialize import (
    SchemaVersionError,
    initialize_database,
    read_schema_version,
    split_statements,
)
from gtaf.infrastructure.db import connect, migration_sql_path


def _sql() -> str:
    """Read the shipped initial migration."""
    return migration_sql_path().read_text(encoding="utf-8")


def test_fresh_database_is_created(db_file: Path) -> None:
    """Case 1: a new path gets the full schema and version 1."""
    conn = connect(db_file)
    try:
        result = initialize_database(conn, _sql())
    finally:
        conn.close()
    assert result.applied is True
    assert result.schema_version == "1"
    assert db_file.exists()


def test_second_run_is_idempotent(db_file: Path) -> None:
    """Case 2: re-running applies nothing and changes no row counts (FR-3)."""
    conn = connect(db_file)
    try:
        initialize_database(conn, _sql())
        before = conn.execute("SELECT count(*) FROM channels").fetchone()
        result = initialize_database(conn, _sql())
        after = conn.execute("SELECT count(*) FROM channels").fetchone()
    finally:
        conn.close()
    assert result.applied is False
    assert before == after


def test_version_zero_is_refused(db_file: Path) -> None:
    """Case 3: an older schema version refuses to proceed and names both versions."""
    conn = connect(db_file)
    try:
        initialize_database(conn, _sql())
        conn.execute("UPDATE schema_meta SET value = '0' WHERE key = 'schema_version'")
        with pytest.raises(SchemaVersionError) as excinfo:
            initialize_database(conn, _sql())
    finally:
        conn.close()
    assert excinfo.value.found == "0"
    assert excinfo.value.supported == "1"


def test_version_two_is_refused(db_file: Path) -> None:
    """Case 4: a newer schema version is refused rather than downgraded."""
    conn = connect(db_file)
    try:
        initialize_database(conn, _sql())
        conn.execute("UPDATE schema_meta SET value = '2' WHERE key = 'schema_version'")
        with pytest.raises(SchemaVersionError):
            initialize_database(conn, _sql())
    finally:
        conn.close()


def test_read_schema_version_on_empty_database(db_file: Path) -> None:
    """A database with no schema_meta table reports no version, rather than an error."""
    conn = connect(db_file)
    try:
        assert read_schema_version(conn) is None
    finally:
        conn.close()


def test_split_statements_drops_blanks() -> None:
    """The runner splits on semicolons and ignores empty fragments."""
    assert split_statements("SELECT 1; SELECT 2;;") == ["SELECT 1", "SELECT 2"]


def test_split_statements_ignores_semicolons_inside_comments() -> None:
    """Regression: a comment containing a semicolon must not be cut into a fake statement.

    This is the exact bug that produced 'unterminated quoted identifier' on the first run of
    the initial migration: the header comment said `splits on ";".`.
    """
    sql = '-- a comment with a ; and a "quote\nSELECT 1;\n-- another ; comment\nSELECT 2;'
    assert split_statements(sql) == ["SELECT 1", "SELECT 2"]


def test_empty_migration_is_refused(db_file: Path) -> None:
    """An empty migration must not produce an unversioned database."""
    conn = connect(db_file)
    try:
        with pytest.raises(ValueError, match="empty"):
            initialize_database(conn, "  \n ; \n")
    finally:
        conn.close()
