"""DuckDB connection adapter: the single place that knows the database is DuckDB.

Implements the concurrency rule of D-005: one writer, read-only readers, and a lock collision
reported as a legible, non-retried failure rather than an intermittent one.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

import duckdb

from gtaf.application.initialize import SchemaVersionError, read_schema_version
from gtaf.domain.invariants import SUPPORTED_SCHEMA_VERSION

_LOCK_MARKERS: Final[tuple[str, ...]] = (
    "could not set lock",
    "conflicting lock",
    "database is locked",
)


class DatabaseLockedError(RuntimeError):
    """Raised when another process holds the database's write lock (D-005, FR-8).

    This is a normal operating condition, not a bug: the scheduled collector and the workbench
    share one file. Callers must report it and stop, never retry in a loop.
    """


class DatabaseNotFoundError(RuntimeError):
    """Raised when a database is opened read-only but does not exist."""


def _is_lock_error(message: str) -> bool:
    """Return True when a driver message describes a lock collision."""
    lowered = message.casefold()
    return any(marker in lowered for marker in _LOCK_MARKERS)


def connect(db_path: Path, *, read_only: bool = False) -> duckdb.DuckDBPyConnection:
    """Open a DuckDB connection, translating a lock collision into a typed error.

    Args:
        db_path: Database file. Its parent must exist.
        read_only: Open read-only (readers never write — D-005).

    Returns:
        An open connection.

    Raises:
        DatabaseNotFoundError: If ``read_only`` is set and the file is absent.
        DatabaseLockedError: If another process holds the write lock.
    """
    if read_only and not db_path.exists():
        raise DatabaseNotFoundError(
            f"database not found: {db_path} (run `gtaf init-db` first)"
        )
    try:
        return duckdb.connect(str(db_path), read_only=read_only)
    except duckdb.Error as exc:
        message = str(exc)
        if _is_lock_error(message):
            raise DatabaseLockedError(
                f"database is locked by another process: {db_path}. Collection and the "
                f"workbench must not write at the same time (D-005). No retry was attempted."
            ) from exc
        raise


def open_database(db_path: Path, *, read_only: bool = True) -> duckdb.DuckDBPyConnection:
    """Open a connection and enforce the schema-version gate (FR-2, FR-13, INV-1).

    Args:
        db_path: Database file.
        read_only: Open read-only. Readers are the default because only the collector writes.

    Returns:
        An open, version-checked connection.

    Raises:
        DatabaseNotFoundError: If the file is absent and ``read_only`` is set.
        DatabaseLockedError: If the write lock is held elsewhere.
        SchemaVersionError: If the stored version is not the supported one.
    """
    conn = connect(db_path, read_only=read_only)
    version = read_schema_version(conn)
    if version != SUPPORTED_SCHEMA_VERSION:
        conn.close()
        raise SchemaVersionError(version, SUPPORTED_SCHEMA_VERSION)
    return conn


def migration_sql_path() -> Path:
    """Return the path of the initial migration shipped with this package."""
    return Path(__file__).parent / "migrations" / "001_init.sql"
