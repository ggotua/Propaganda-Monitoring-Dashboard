"""Configuration validation tests (SPEC-001 §9 cases 5-10, FR-4…FR-7)."""

from __future__ import annotations

from pathlib import Path

import pytest

from gtaf.application.config import ConfigError
from gtaf.infrastructure.config_io import load_configuration


def test_repository_config_is_valid(config_dir: Path) -> None:
    """The committed corpus definition loads: six channels, validated pattern families."""
    bundle = load_configuration(config_dir)
    assert bundle.channel_count == 6
    assert bundle.programme_count == 8
    assert {c.channel_id for c in bundle.channels} == {
        "imedi",
        "rustavi2",
        "postv",
        "gpb",
        "formula",
        "pirveli",
    }
    assert all(c.youtube_handle.startswith("@") for c in bundle.channels)
    assert all(p.title_patterns or p.playlist_ids for p in bundle.programmes)


def test_handle_without_at_sign_is_rejected(config_factory) -> None:
    """Case 6: a handle missing '@' is rejected with a path-qualified message."""
    directory = config_factory(
        [{"channel_id": "imedi", "name_en": "Imedi", "youtube_handle": "tvimedi"}], []
    )
    with pytest.raises(ConfigError) as excinfo:
        load_configuration(directory)
    assert any("youtube_handle" in message for message in excinfo.value.violations)


def test_duplicate_handle_is_rejected(config_factory) -> None:
    """Case 7: two channels declaring the same handle is an error."""
    directory = config_factory(
        [
            {"channel_id": "imedi", "name_en": "Imedi", "youtube_handle": "@postv"},
            {"channel_id": "postv", "name_en": "POSTV", "youtube_handle": "@postv"},
        ],
        [],
    )
    with pytest.raises(ConfigError) as excinfo:
        load_configuration(directory)
    assert any("declared 2 times" in message for message in excinfo.value.violations)


def test_programme_with_unknown_channel_is_rejected(config_factory) -> None:
    """Case 8: cross-file referential integrity, checked before any database is opened."""
    directory = config_factory(
        [{"channel_id": "imedi", "name_en": "Imedi", "youtube_handle": "@tvimedi"}],
        [
            {
                "programme_id": "ghost_news",
                "channel_id": "imedi2",
                "name_en": "Ghost",
                "type": "news",
                "title_patterns": ["ამბები"],
            }
        ],
    )
    with pytest.raises(ConfigError) as excinfo:
        load_configuration(directory)
    assert any("unknown channel" in message for message in excinfo.value.violations)


def test_invalid_programme_type_is_rejected(config_factory) -> None:
    """Case 9: the type enum is closed."""
    directory = config_factory(
        [{"channel_id": "imedi", "name_en": "Imedi", "youtube_handle": "@tvimedi"}],
        [
            {
                "programme_id": "imedi_doc",
                "channel_id": "imedi",
                "name_en": "Doc",
                "type": "documentary",
                "title_patterns": ["x"],
            }
        ],
    )
    with pytest.raises(ConfigError) as excinfo:
        load_configuration(directory)
    assert any("type" in message for message in excinfo.value.violations)


def test_programme_that_can_never_match_is_rejected(config_factory) -> None:
    """Case 10: no patterns and no playlists means the programme is unclassifiable."""
    directory = config_factory(
        [{"channel_id": "imedi", "name_en": "Imedi", "youtube_handle": "@tvimedi"}],
        [
            {
                "programme_id": "imedi_nothing",
                "channel_id": "imedi",
                "name_en": "Nothing",
                "type": "news",
                "title_patterns": [],
                "playlist_ids": [],
            }
        ],
    )
    with pytest.raises(ConfigError) as excinfo:
        load_configuration(directory)
    assert any("neither title_patterns nor playlist_ids" in m for m in excinfo.value.violations)


def test_all_violations_are_reported_together(config_factory) -> None:
    """FR-4: one run must report every problem, not stop at the first."""
    directory = config_factory(
        [
            {"channel_id": "imedi", "name_en": "Imedi", "youtube_handle": "tvimedi"},
            {"channel_id": "postv", "name_en": "POSTV", "youtube_handle": "postv"},
        ],
        [
            {
                "programme_id": "bad_one",
                "channel_id": "nope",
                "name_en": "Bad",
                "type": "news",
                "title_patterns": [],
            },
            {
                "programme_id": "bad_two",
                "channel_id": "nope",
                "name_en": "Bad2",
                "type": "news",
                "title_patterns": ["x"],
            },
        ],
    )
    with pytest.raises(ConfigError) as excinfo:
        load_configuration(directory)
    assert len(excinfo.value.violations) >= 4


def test_unknown_extra_key_is_rejected(config_factory) -> None:
    """Shape rules are closed: a typo'd key must not be silently ignored."""
    directory = config_factory(
        [
            {
                "channel_id": "imedi",
                "name_en": "Imedi",
                "youtube_handle": "@tvimedi",
                "youtube_chanel_id": "typo",
            }
        ],
        [],
    )
    with pytest.raises(ConfigError) as excinfo:
        load_configuration(directory)
    assert any("youtube_chanel_id" in message for message in excinfo.value.violations)


def test_missing_file_is_reported(config_factory) -> None:
    """A missing config file is a ConfigError naming the file, not a traceback."""
    directory = config_factory([], [])
    (directory / "programmes.yaml").unlink()
    with pytest.raises(ConfigError) as excinfo:
        load_configuration(directory)
    assert any("programmes.yaml" in message for message in excinfo.value.violations)


def test_unsupported_config_schema_version_is_rejected(config_factory) -> None:
    """Configuration carries its own version, separate from the database schema version."""
    directory = config_factory(
        [{"channel_id": "imedi", "name_en": "Imedi", "youtube_handle": "@tvimedi"}], []
    )
    (directory / "channels.yaml").write_text(
        "schema_version: 99\nchannels: []\n", encoding="utf-8"
    )
    with pytest.raises(ConfigError) as excinfo:
        load_configuration(directory)
    assert any("schema_version" in message for message in excinfo.value.violations)
