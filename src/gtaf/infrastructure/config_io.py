"""Configuration file loading: YAML in, validated domain objects out.

Shape rules live here (pydantic, FR-4); cross-file rules live in
``gtaf.application.config.validate_cross_references``. Everything is aggregate-validated so a
single run reports every problem.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from gtaf.application.config import ConfigBundle, ConfigError, validate_cross_references
from gtaf.domain.models import Channel, Programme, ProgrammeType

CONFIG_SCHEMA_VERSION = 1

_CHANNEL_ID = r"^[a-z][a-z0-9_]{1,30}$"
_PROGRAMME_ID = r"^[a-z][a-z0-9_]{1,40}$"
_HANDLE = r"^@[A-Za-z0-9._-]{2,50}$"


class ChannelDoc(BaseModel):
    """Shape rules for one entry of ``channels.yaml``."""

    model_config = ConfigDict(extra="forbid")

    channel_id: str = Field(pattern=_CHANNEL_ID)
    name_en: str = Field(min_length=1)
    name_ka: str | None = None
    youtube_handle: str = Field(pattern=_HANDLE)
    active: bool = True

    def to_domain(self) -> Channel:
        """Convert to the domain entity."""
        return Channel(
            channel_id=self.channel_id,
            name_en=self.name_en,
            name_ka=self.name_ka,
            youtube_handle=self.youtube_handle,
            active=self.active,
        )


class ProgrammeDoc(BaseModel):
    """Shape rules for one entry of ``programmes.yaml``."""

    model_config = ConfigDict(extra="forbid")

    programme_id: str = Field(pattern=_PROGRAMME_ID)
    channel_id: str = Field(min_length=1)
    name_en: str = Field(min_length=1)
    name_ka: str | None = None
    type: ProgrammeType
    title_patterns: list[str] = Field(default_factory=list)
    playlist_ids: list[str] = Field(default_factory=list)
    active: bool = True

    def to_domain(self) -> Programme:
        """Convert to the domain entity."""
        return Programme(
            programme_id=self.programme_id,
            channel_id=self.channel_id,
            name_en=self.name_en,
            name_ka=self.name_ka,
            type=self.type,
            title_patterns=tuple(self.title_patterns),
            playlist_ids=tuple(self.playlist_ids),
            active=self.active,
        )


def read_yaml(path: Path) -> Any:
    """Read a YAML document.

    Args:
        path: File to read, UTF-8.

    Returns:
        The parsed document.

    Raises:
        ConfigError: If the file is missing, unreadable or not valid YAML.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ConfigError([f"{path.name}: file not found at {path}"]) from exc
    except OSError as exc:
        raise ConfigError([f"{path.name}: cannot be read ({exc})"]) from exc
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError([f"{path.name}: not valid YAML ({exc})"]) from exc


def _entries(doc: Any, key: str, filename: str, violations: list[str]) -> list[Any]:
    """Extract the entry list from a document, recording structural problems.

    Args:
        doc: Parsed YAML document.
        key: Top-level key holding the list.
        filename: Filename for messages.
        violations: Accumulator for messages.

    Returns:
        The raw entries, or an empty list when the document is malformed.
    """
    if not isinstance(doc, dict):
        violations.append(
            f"{filename}: top level must be a mapping with 'schema_version' and '{key}'"
        )
        return []
    version = doc.get("schema_version")
    if version != CONFIG_SCHEMA_VERSION:
        violations.append(
            f"{filename}: unsupported schema_version {version!r} "
            f"(expected {CONFIG_SCHEMA_VERSION})"
        )
    raw = doc.get(key)
    if not isinstance(raw, list):
        violations.append(f"{filename}: '{key}' must be a list")
        return []
    return raw


def _parse_entries[T: (ChannelDoc, ProgrammeDoc)](
    raw: list[Any],
    model: type[T],
    filename: str,
    key: str,
    violations: list[str],
) -> list[T]:
    """Validate each raw entry, accumulating messages instead of stopping at the first.

    Args:
        raw: Raw entries from YAML.
        model: Pydantic model to validate against.
        filename: Filename for messages.
        key: List key, for indexing messages.
        violations: Accumulator for messages.

    Returns:
        Successfully parsed entries; invalid ones are skipped and reported.
    """
    parsed: list[T] = []
    for index, entry in enumerate(raw):
        try:
            parsed.append(model.model_validate(entry))
        except ValidationError as exc:
            for error in exc.errors():
                location = ".".join(str(part) for part in error["loc"])
                violations.append(f"{filename}: {key}[{index}].{location}: {error['msg']}")
    return parsed


def load_configuration(config_dir: Path) -> ConfigBundle:
    """Load and fully validate the corpus configuration.

    Args:
        config_dir: Directory containing ``channels.yaml`` and ``programmes.yaml``.

    Returns:
        A validated ``ConfigBundle``.

    Raises:
        ConfigError: Listing every violation found, from both files.
    """
    violations: list[str] = []

    channels_doc = read_yaml(config_dir / "channels.yaml")
    programmes_doc = read_yaml(config_dir / "programmes.yaml")

    raw_channels = _entries(channels_doc, "channels", "channels.yaml", violations)
    raw_programmes = _entries(programmes_doc, "programmes", "programmes.yaml", violations)

    channel_docs = _parse_entries(raw_channels, ChannelDoc, "channels.yaml", "channels", violations)
    programme_docs = _parse_entries(
        raw_programmes, ProgrammeDoc, "programmes.yaml", "programmes", violations
    )

    channels = [doc.to_domain() for doc in channel_docs]
    programmes = [doc.to_domain() for doc in programme_docs]

    # Cross-file rules run even when some entries failed shape validation, so one command still
    # reports the shape *and* the referential problems together (FR-4) rather than making the
    # operator fix them in two rounds.
    try:
        bundle = validate_cross_references(channels, programmes)
    except ConfigError as exc:
        violations.extend(exc.violations)
    else:
        if not violations:
            return bundle

    raise ConfigError(violations)


__all__ = [
    "CONFIG_SCHEMA_VERSION",
    "ChannelDoc",
    "ProgrammeDoc",
    "load_configuration",
    "read_yaml",
]
