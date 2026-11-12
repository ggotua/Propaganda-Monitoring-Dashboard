"""CLI contract tests: exit codes are part of the interface (SPEC-001 §8)."""

from __future__ import annotations

from pathlib import Path

import pytest

from gtaf.cli import EXIT_CONFIG, EXIT_ERROR, EXIT_OK, EXIT_SCHEMA, main
from gtaf.infrastructure.db import connect


def test_init_db_creates_and_reports(tmp_path: Path, capsys) -> None:
    """Case 1 through the CLI: exit 0, file exists, message names the version."""
    db_path = tmp_path / "new.duckdb"
    code = main(["init-db", str(db_path), "--log-dir", str(tmp_path / "logs")])
    captured = capsys.readouterr()
    assert code == EXIT_OK
    assert db_path.exists()
    assert "schema_version=1" in captured.out


def test_init_db_twice_is_idempotent(tmp_path: Path, capsys) -> None:
    """FR-3 through the CLI: the second run says there is nothing to do."""
    db_path = tmp_path / "new.duckdb"
    log_dir = str(tmp_path / "logs")
    assert main(["init-db", str(db_path), "--log-dir", log_dir]) == EXIT_OK
    capsys.readouterr()
    assert main(["init-db", str(db_path), "--log-dir", log_dir]) == EXIT_OK
    assert "nothing to do" in capsys.readouterr().out


def test_schema_version_prints_version(initialized_db: Path, capsys) -> None:
    """FR-2: the version can be read back from a command line."""
    assert main(["schema-version", str(initialized_db)]) == EXIT_OK
    assert capsys.readouterr().out.strip() == "1"


def test_schema_version_on_missing_database(tmp_path: Path) -> None:
    """A missing database is an error (exit 1), not an empty result."""
    assert main(["schema-version", str(tmp_path / "absent.duckdb")]) == EXIT_ERROR


def test_unsupported_version_exits_three(initialized_db: Path) -> None:
    """FR-2: an unknown version is its own exit code so scripts can distinguish it."""
    conn = connect(initialized_db)
    try:
        conn.execute("UPDATE schema_meta SET value = '9' WHERE key = 'schema_version'")
    finally:
        conn.close()
    assert main(["schema-version", str(initialized_db)]) == EXIT_SCHEMA


def test_check_config_on_repository_config(config_dir: Path, capsys) -> None:
    """FR-7: valid configuration prints counts and exits 0."""
    assert main(["check-config", "--config-dir", str(config_dir)]) == EXIT_OK
    out = capsys.readouterr().out
    assert "6 channels" in out
    assert "12 programmes" in out


def test_check_config_invalid_exits_two(config_factory, capsys) -> None:
    """FR-4: invalid configuration exits 2 and prints every violation to stderr."""
    directory = config_factory(
        [{"channel_id": "imedi", "name_en": "Imedi", "youtube_handle": "no-at-sign"}], []
    )
    assert main(["check-config", "--config-dir", str(directory)]) == EXIT_CONFIG
    assert "youtube_handle" in capsys.readouterr().err


def test_doctor_reports_healthy(capsys) -> None:
    """FR-12: with the venv installed, doctor passes."""
    code = main(["doctor"])
    out = capsys.readouterr().out
    assert "python" in out
    assert "duckdb" in out
    assert code == EXIT_OK


def test_doctor_json_mode(capsys) -> None:
    """FR-12: JSON mode is machine-readable."""
    import json

    code = main(["doctor", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == EXIT_OK
    assert payload["ok"] is True
    assert any(check["name"] == "db_write_probe" for check in payload["checks"])


def test_unknown_command_fails_cleanly() -> None:
    """argparse rejects an unknown command with SystemExit(2), before any work is done."""
    with pytest.raises(SystemExit):
        main(["nonsense"])
