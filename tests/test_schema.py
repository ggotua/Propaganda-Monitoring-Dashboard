"""Schema, invariant and timezone tests (SPEC-001 §9 cases 11-16, INV-1…INV-9)."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import duckdb
import pytest

from gtaf.application.initialize import SchemaVersionError
from gtaf.domain.invariants import (
    SUPPORTED_SCHEMA_VERSION,
    are_caption_indices_contiguous,
    is_finished_run_consistent,
    is_segment_within_bounds,
    is_supported_schema_version,
    is_valid_caption_span,
    local_date_of,
)
from gtaf.infrastructure import db as db_module
from gtaf.infrastructure.db import DatabaseLockedError, connect, open_database


def test_all_tables_exist(initialized_db: Path) -> None:
    """The migration creates every table SPEC-001 §5.1 declares."""
    conn = connect(initialized_db, read_only=True)
    try:
        rows = conn.execute(
            "SELECT table_name FROM information_schema.tables ORDER BY table_name"
        ).fetchall()
    finally:
        conn.close()
    tables = {str(row[0]) for row in rows}
    assert {
        "schema_meta",
        "channels",
        "programmes",
        "videos",
        "captions",
        "segments",
        "runs",
        "llm_calls",
        "validation",
    } <= tables


def test_schema_version_is_supported(initialized_db: Path) -> None:
    """FR-1: a fresh database reports the supported version."""
    conn = connect(initialized_db, read_only=True)
    try:
        row = conn.execute("SELECT value FROM schema_meta WHERE key = 'schema_version'").fetchone()
    finally:
        conn.close()
    assert row is not None
    assert row[0] == SUPPORTED_SCHEMA_VERSION


def test_caption_with_zero_length_is_rejected(initialized_db: Path) -> None:
    """Case 11: the boundary itself is invalid — must be strictly greater, not >=."""
    conn = connect(initialized_db)
    try:
        conn.execute(
            "INSERT INTO channels VALUES ('imedi', 'Imedi', NULL, '@tvimedi', NULL, TRUE)"
        )
        conn.execute(
            "INSERT INTO videos VALUES ('v1', 'imedi', NULL, '2026-10-01 19:00:00', "
            "'2026-10-01', 't', 60, 'auto', 'ka', 'captioned', '2026-10-01 20:00:00')"
        )
        with pytest.raises(duckdb.Error):
            conn.execute(
                "INSERT INTO captions VALUES ('v1', 0, 1.0, 1.0, 'hello')"
            )
    finally:
        conn.close()


def test_caption_just_above_boundary_is_accepted(initialized_db: Path) -> None:
    """Case 12: one thousandth of a second above the boundary is valid."""
    conn = connect(initialized_db)
    try:
        conn.execute(
            "INSERT INTO channels VALUES ('imedi', 'Imedi', NULL, '@tvimedi', NULL, TRUE)"
        )
        conn.execute(
            "INSERT INTO videos VALUES ('v1', 'imedi', NULL, '2026-10-01 19:00:00', "
            "'2026-10-01', 't', 60, 'auto', 'ka', 'captioned', '2026-10-01 20:00:00')"
        )
        conn.execute("INSERT INTO captions VALUES ('v1', 0, 1.0, 1.001, 'hello')")
        row = conn.execute("SELECT count(*) FROM captions").fetchone()
    finally:
        conn.close()
    assert row is not None
    assert row[0] == 1


def test_read_only_connection_cannot_write(initialized_db: Path) -> None:
    """FR-13: a reader must fail rather than silently write (D-005)."""
    conn = open_database(initialized_db, read_only=True)
    try:
        with pytest.raises(duckdb.Error):
            conn.execute("INSERT INTO channels VALUES ('x', 'X', NULL, '@x', NULL, TRUE)")
    finally:
        conn.close()


def test_unsupported_version_is_refused_on_open(initialized_db: Path) -> None:
    """FR-2: an unknown stored version refuses to open, naming both versions."""
    conn = connect(initialized_db)
    try:
        conn.execute("UPDATE schema_meta SET value = '99' WHERE key = 'schema_version'")
    finally:
        conn.close()

    with pytest.raises(SchemaVersionError) as excinfo:
        open_database(initialized_db, read_only=True)
    assert excinfo.value.found == "99"
    assert excinfo.value.supported == SUPPORTED_SCHEMA_VERSION


def test_lock_collision_is_translated(monkeypatch, db_file: Path) -> None:
    """FR-8: a driver lock message becomes DatabaseLockedError, and no retry is attempted."""
    calls = {"n": 0}

    def fake_connect(*args: object, **kwargs: object) -> object:
        calls["n"] += 1
        raise duckdb.Error('Could not set lock on file "x": Conflicting lock is held')

    monkeypatch.setattr(db_module.duckdb, "connect", fake_connect)
    with pytest.raises(DatabaseLockedError) as excinfo:
        db_module.connect(db_file, read_only=False)
    assert "locked" in str(excinfo.value)
    assert calls["n"] == 1, "a lock collision must not be retried"


def test_missing_read_only_database_is_reported(tmp_path: Path) -> None:
    """Opening a non-existent database read-only is an error, not an empty database."""
    from gtaf.infrastructure.db import DatabaseNotFoundError

    with pytest.raises(DatabaseNotFoundError):
        connect(tmp_path / "absent.duckdb", read_only=True)


def test_tbilisi_date_crosses_midnight_utc() -> None:
    """Case 14: 21:30 UTC on 31 Oct is 01:30 on 1 Nov in Tbilisi (UTC+4)."""
    assert local_date_of(datetime(2026, 10, 31, 21, 30)) == date(2026, 11, 1)


def test_tbilisi_date_just_before_midnight() -> None:
    """Case 15: 19:30 UTC is 23:30 local — still the same date."""
    assert local_date_of(datetime(2026, 10, 31, 19, 30)) == date(2026, 10, 31)


def test_tbilisi_boundary_is_exact() -> None:
    """20:00 UTC is exactly midnight local: the first instant of the next date."""
    assert local_date_of(datetime(2026, 10, 31, 20, 0)) == date(2026, 11, 1)
    assert local_date_of(datetime(2026, 10, 31, 19, 59, 59)) == date(2026, 10, 31)


@pytest.mark.parametrize(
    ("start_s", "end_s", "expected"),
    [
        (0.0, 1.0, True),
        (1.0, 1.0, False),
        (2.0, 1.0, False),
        (-1.0, 1.0, False),
    ],
)
def test_caption_span_predicate(start_s: float, end_s: float, expected: bool) -> None:
    """INV-4 as a pure predicate, including the reversed-span partition."""
    assert is_valid_caption_span(start_s, end_s) is expected


def test_caption_indices_contiguity() -> None:
    """Case 13: a gap in cue indices is a violation, not a tolerable irregularity."""
    assert are_caption_indices_contiguous([0, 1, 2]) is True
    assert are_caption_indices_contiguous([]) is True
    assert are_caption_indices_contiguous([0, 1, 3]) is False
    assert are_caption_indices_contiguous([1, 2]) is False


def test_segment_bounds() -> None:
    """INV-7: a segment may not run past the end of its video."""
    assert is_segment_within_bounds(0.0, 10.0, 60) is True
    assert is_segment_within_bounds(50.0, 70.0, 60) is False
    assert is_segment_within_bounds(0.0, 10.0, None) is True
    assert is_segment_within_bounds(5.0, 5.0, 60) is False


def test_schema_version_predicate() -> None:
    """INV-1: absent or unknown versions are unsupported."""
    assert is_supported_schema_version(SUPPORTED_SCHEMA_VERSION) is True
    assert is_supported_schema_version("99") is False
    assert is_supported_schema_version(None) is False


def test_run_consistency_predicate() -> None:
    """INV-8: an 'ok' run must carry a finish time; other statuses may not."""
    assert is_finished_run_consistent("ok", datetime(2026, 1, 1)) is True
    assert is_finished_run_consistent("ok", None) is False
    assert is_finished_run_consistent("running", None) is True
    assert is_finished_run_consistent("failed", None) is True
