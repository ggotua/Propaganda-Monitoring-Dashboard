"""Configuration use cases: assemble a validated corpus definition.

Shape validation (types, patterns, enums) happens in ``infrastructure.config_io`` with pydantic.
This module owns the **cross-file** rules that no single entry can check, and it aggregates
every violation rather than raising on the first one (FR-4): fixing configuration one error per
run is the difference between one edit and ten.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from gtaf.domain.models import Channel, Programme


class ConfigError(Exception):
    """Raised when the corpus configuration violates one or more rules.

    Attributes:
        violations: Human-readable messages, each naming the file path and the offending value.
    """

    def __init__(self, violations: Sequence[str]) -> None:
        self.violations: tuple[str, ...] = tuple(violations)
        joined = "\n  - ".join(self.violations)
        super().__init__(f"{len(self.violations)} configuration violation(s):\n  - {joined}")


@dataclass(frozen=True, slots=True)
class ConfigBundle:
    """A validated corpus definition.

    Attributes:
        channels: Channels in scope, in file order.
        programmes: Programme pattern families, in file order.
    """

    channels: tuple[Channel, ...]
    programmes: tuple[Programme, ...]

    @property
    def channel_count(self) -> int:
        """Number of configured channels."""
        return len(self.channels)

    @property
    def programme_count(self) -> int:
        """Number of configured programmes."""
        return len(self.programmes)


def validate_cross_references(
    channels: Sequence[Channel],
    programmes: Sequence[Programme],
) -> ConfigBundle:
    """Check the rules that span both configuration files, and return the bundle.

    Checks performed: duplicate channel ids, duplicate handles, duplicate programme ids,
    programmes pointing at an unknown channel, and programmes that could never match anything
    (no title pattern and no playlist).

    Args:
        channels: Channels parsed from ``channels.yaml``.
        programmes: Programmes parsed from ``programmes.yaml``.

    Returns:
        The same entries, as a ``ConfigBundle``.

    Raises:
        ConfigError: If any rule is violated; the message lists all violations.
    """
    violations: list[str] = []

    for channel_id, count in Counter(c.channel_id for c in channels).items():
        if count > 1:
            violations.append(f"channels.yaml: channel_id '{channel_id}' declared {count} times")

    for handle, count in Counter(c.youtube_handle.casefold() for c in channels).items():
        if count > 1:
            violations.append(f"channels.yaml: youtube_handle '{handle}' declared {count} times")

    for programme_id, count in Counter(p.programme_id for p in programmes).items():
        if count > 1:
            violations.append(
                f"programmes.yaml: programme_id '{programme_id}' declared {count} times"
            )

    known = {c.channel_id for c in channels}
    for programme in programmes:
        if programme.channel_id not in known:
            violations.append(
                f"programmes.yaml: {programme.programme_id}: unknown channel "
                f"'{programme.channel_id}' (not in channels.yaml)"
            )
        if not programme.title_patterns and not programme.playlist_ids:
            violations.append(
                f"programmes.yaml: {programme.programme_id}: has neither title_patterns nor "
                f"playlist_ids, so it could never match a video"
            )

    if not channels:
        violations.append("channels.yaml: no channels configured")

    if violations:
        raise ConfigError(violations)

    return ConfigBundle(channels=tuple(channels), programmes=tuple(programmes))
