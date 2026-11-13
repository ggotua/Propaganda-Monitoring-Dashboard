"""Pure predicates that encode the spec's invariants (INV-1…INV-9).

Callers use these as **assertions**: a False result means the pipeline is wrong and must fail at
the point of violation, not three stages later (exception-vs-assertion rule, SPEC-001 §6).

Kept free of I/O and of any database type so the same rule can be tested without a database and
reused by SPEC-002/003 rather than restated (DRY).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta, timezone

# Georgia has observed a fixed UTC+4 with no daylight saving since 2005, so a fixed offset is
# the honest representation for this corpus (which starts 2026-10-01, i.e. entirely "recent").
# Using zoneinfo here would additionally require the `tzdata` package on Windows — a new
# third-party dependency for no benefit at this corpus's dates (SPEC-001 §12, Boundaries).
# If Georgia ever reinstates DST, this is the single constant to change.
TBILISI_OFFSET = timezone(timedelta(hours=4), "Asia/Tbilisi")

# The schema version this code understands (INV-1). Bumped to 2 when topic tables landed (SPEC-007).
SUPPORTED_SCHEMA_VERSION = "2"


def local_date_of(instant_utc: datetime) -> date:
    """Return the Tbilisi local date of a naive-UTC instant.

    Args:
        instant_utc: A naive datetime interpreted as UTC.

    Returns:
        The date in Tbilisi local time (UTC+4).

    Notes:
        A naive value is intentionally treated as UTC; D-009 fixes that convention, and an
        aware value is converted properly rather than reinterpreted.
    """
    if instant_utc.tzinfo is None:
        return instant_utc.replace(tzinfo=UTC).astimezone(TBILISI_OFFSET).date()
    return instant_utc.astimezone(TBILISI_OFFSET).date()


def is_valid_caption_span(start_s: float, end_s: float) -> bool:
    """Return True when a caption cue has a positive duration and a non-negative start (INV-4).

    Args:
        start_s: Cue start in seconds.
        end_s: Cue end in seconds.

    Returns:
        True when ``end_s > start_s >= 0``.
    """
    return start_s >= 0 and end_s > start_s


def are_caption_indices_contiguous(indices: Sequence[int]) -> bool:
    """Return True when caption cue indices are exactly ``0..n-1`` (INV-3).

    Args:
        indices: Cue indices in the order they were read or written.

    Returns:
        True when the sorted indices form a contiguous run starting at zero.
    """
    if not indices:
        return True
    ordered = sorted(indices)
    return ordered[0] == 0 and ordered == list(range(len(ordered)))


def is_segment_within_bounds(start_s: float, end_s: float, duration_s: int | None) -> bool:
    """Return True when a segment lies inside its video (INV-7).

    Args:
        start_s: Segment start in seconds.
        end_s: Segment end in seconds.
        duration_s: Video duration, or None when unpublished.

    Returns:
        True when the span is valid and — if the duration is known — does not exceed it.
    """
    if not is_valid_caption_span(start_s, end_s):
        return False
    if duration_s is None:
        return True
    return end_s <= float(duration_s)


def is_supported_schema_version(found: str | None) -> bool:
    """Return True when a stored schema version is one this code can operate on (INV-1).

    Args:
        found: Value read from ``schema_meta``, or None when the table/row is absent.

    Returns:
        True only for the supported version.
    """
    return found == SUPPORTED_SCHEMA_VERSION


def is_finished_run_consistent(status: str, finished_at: datetime | None) -> bool:
    """Return True when a run's status and finish time agree (INV-8).

    Args:
        status: Run status value.
        finished_at: Finish instant, or None while running.

    Returns:
        False when a run claims to be ``ok`` without a finish time; True otherwise.
    """
    if status == "ok":
        return finished_at is not None
    return True
