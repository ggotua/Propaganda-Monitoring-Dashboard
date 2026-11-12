"""Shared fixtures.

Fixtures deliberately build their own minimal config files rather than mutating the repository's
``config/``: a test that needs an invalid handle must not be able to leave the committed corpus
invalid.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def repo_root() -> Path:
    """Absolute path of the repository root."""
    return REPO_ROOT


@pytest.fixture
def config_dir(repo_root: Path) -> Path:
    """The committed configuration directory."""
    return repo_root / "config"


@pytest.fixture
def db_file(tmp_path: Path) -> Path:
    """Path for a fresh database file (not yet created)."""
    return tmp_path / "gtaf_test.duckdb"


@pytest.fixture
def initialized_db(db_file: Path) -> Path:
    """A database with the initial schema applied."""
    from gtaf.application.initialize import initialize_database
    from gtaf.infrastructure.db import connect, migration_sql_path

    sql = migration_sql_path().read_text(encoding="utf-8")
    conn = connect(db_file)
    try:
        initialize_database(conn, sql)
    finally:
        conn.close()
    return db_file


@pytest.fixture
def config_factory(tmp_path: Path):
    """Return a factory that writes a pair of config files and yields their directory."""

    def _write(channels: list[dict[str, Any]], programmes: list[dict[str, Any]]) -> Path:
        directory = tmp_path / "cfg"
        directory.mkdir(exist_ok=True)
        (directory / "channels.yaml").write_text(
            yaml.safe_dump({"schema_version": 1, "channels": channels}, allow_unicode=True),
            encoding="utf-8",
        )
        (directory / "programmes.yaml").write_text(
            yaml.safe_dump({"schema_version": 1, "programmes": programmes}, allow_unicode=True),
            encoding="utf-8",
        )
        return directory

    return _write
