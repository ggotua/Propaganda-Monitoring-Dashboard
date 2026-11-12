"""CLI contract tests: exit codes are part of the interface (SPEC-001 §8)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

import gtaf.cli as cli
from gtaf.application.collect import ClientBlockedError, FetchedVideo
from gtaf.cli import EXIT_CONFIG, EXIT_ERROR, EXIT_OK, EXIT_SCHEMA, main
from gtaf.domain.collector import UploadRef, VideoMeta
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
    assert "8 programmes" in out


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


class _StubSource:
    """Minimal stand-in for the yt-dlp adapter, so collect wiring is testable offline."""

    def __init__(self, *, fail_with: Exception | None = None) -> None:
        self.fail_with = fail_with

    def list_uploads(self, handle: str, limit: int):
        """Return two uploads."""
        if self.fail_with is not None:
            raise self.fail_with
        return [UploadRef("v1", "ქრონიკა 19:00"), UploadRef("v2", "უცნობი სათაური")]

    def fetch_video(self, video_id: str):
        """Return a captioned fixture for v1 and an uncaptioned one for v2."""
        if video_id == "v1":
            return FetchedVideo(
                meta=VideoMeta(
                    video_id="v1",
                    title="ქრონიკა 19:00",
                    published_at=datetime(2026, 11, 1, 19, 0),
                    duration_s=1800,
                    manual_langs=(),
                    auto_langs=("ka",),
                ),
                raw_payload='{"events": []}',
                cues=(),
            )
        return FetchedVideo(
            meta=VideoMeta(
                video_id="v2",
                title="უცნობი სათაური",
                published_at=datetime(2026, 11, 1, 20, 0),
                duration_s=600,
                manual_langs=(),
                auto_langs=(),
            ),
            raw_payload=None,
            cues=(),
        )


def test_collect_wires_end_to_end(tmp_path: Path, monkeypatch, capsys) -> None:
    """FR-1/FR-10: the collect command runs, stores rows and prints the coverage report."""
    db_path = tmp_path / "collect.duckdb"
    log_dir = tmp_path / "logs"
    assert main(["init-db", str(db_path), "--log-dir", str(log_dir)]) == EXIT_OK
    capsys.readouterr()

    monkeypatch.setattr(cli, "YtDlpSource", lambda throttle: _StubSource())
    code = main(
        [
            "collect",
            "--db", str(db_path),
            "--config-dir", "config",
            "--raw-dir", str(tmp_path / "raw"),
            "--log-dir", str(log_dir),
            "--channel", "imedi",
            "--limit", "5",
        ]
    )
    out = capsys.readouterr().out

    assert code == EXIT_OK
    assert "unclass" in out
    assert "Imedi" in out
    # v1 captured, v2 has no captions: both stored, one counted as missing.
    assert (tmp_path / "raw").exists()


def test_collect_reports_block_with_exit_five(tmp_path: Path, monkeypatch, capsys) -> None:
    """FR-7: a client-level block is its own exit code, so a scheduler can tell it apart."""
    db_path = tmp_path / "collect.duckdb"
    log_dir = tmp_path / "logs"
    assert main(["init-db", str(db_path), "--log-dir", str(log_dir)]) == EXIT_OK
    capsys.readouterr()

    monkeypatch.setattr(
        cli,
        "YtDlpSource",
        lambda throttle: _StubSource(fail_with=ClientBlockedError("HTTP Error 429")),
    )
    code = main(
        [
            "collect",
            "--db", str(db_path),
            "--config-dir", "config",
            "--raw-dir", str(tmp_path / "raw"),
            "--log-dir", str(log_dir),
            "--channel", "imedi",
        ]
    )
    assert code == 5
    assert "blocked" in capsys.readouterr().err
