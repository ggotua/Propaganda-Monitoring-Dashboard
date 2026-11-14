"""Segmentation (SPEC-004 fixed windows, SPEC-006 pause-aware).

Pure functions: sentences in, segment drafts out. Three rules coexist because the choice is
empirical:

- ``fixed`` — cut every ~90 s regardless of content. Deliberately disposable, and its `seg_method`
  value exists so its output can never be mistaken for real segmentation.
- ``pause`` — cut where speech actually pauses, with duration bounds as a fallback. A silence
  between
  sentences is the cheapest observable signal of a topic boundary, and unlike an LLM it is
  deterministic and free.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from gtaf.domain.normalise import Sentence

SEG_METHOD = "fixed"
SEG_VERSION = "1"

SEG_METHOD_PAUSE = "pause"
SEG_VERSION_PAUSE = "1"

SEG_METHOD_DRIFT = "drift"
SEG_VERSION_DRIFT = "1"

TARGET_S = 90.0
MAX_S = 240.0
MIN_S = 20.0

# Measured from the corpus: news reading is continuous, so a gap of two seconds is a real break —
# a correspondent handover, a tape change, or a new item. Shorter gaps are sentence rhythm.
PAUSE_S = 1.8
PAUSE_MIN_S = 15.0
PAUSE_TARGET_S = 60.0
PAUSE_MAX_S = 150.0


@dataclass(frozen=True, slots=True)
class SegmentDraft:
    """A segment ready to persist.

    Attributes:
        segment_id: Deterministic id, ``"{video_id}:{start_ms:08d}"``.
        start_s: Start of the first contributing sentence.
        end_s: End of the last contributing sentence.
        text: Sentences joined by a single space.
    """

    segment_id: str
    start_s: float
    end_s: float
    text: str


def _draft(video_id: str, group: Sequence[Sentence], *, prefix: str = "") -> SegmentDraft:
    """Build a segment draft from a group of sentences.

    Args:
        video_id: Owning video.
        group: Consecutive sentences forming the segment.
        prefix: Method discriminator inserted into the id.

    Returns:
        The draft, with a deterministic id derived from the start time in whole milliseconds so a
        re-run reproduces byte-identical ids.

    Notes:
        The prefix exists because two segmentations of the same video can start a segment at the
        same millisecond: measured 2026-11-14, `ZZGoZutVr7o:00000199` was produced by both the
        fixed-window and drift runs and the primary key rejected the second. Method-scoped ids make
        that collision
        impossible; the fixed method keeps an empty prefix so its existing rows stay valid.
    """
    start_s = group[0].start_s
    end_s = group[-1].end_s
    return SegmentDraft(
        segment_id=f"{video_id}:{prefix}{round(start_s * 1000):08d}",
        start_s=start_s,
        end_s=end_s,
        text=" ".join(sentence.text for sentence in group),
    )


def segment_sentences(
    sentences: Sequence[Sentence],
    video_id: str,
    *,
    target_s: float = TARGET_S,
    max_s: float = MAX_S,
    min_s: float = MIN_S,
) -> tuple[SegmentDraft, ...]:
    """Group sentences into contiguous segments of roughly ``target_s`` seconds.

    Args:
        sentences: Time-ordered sentences for one video.
        video_id: Owning video id, used to build deterministic segment ids.
        target_s: Window length to aim for; a segment closes once it reaches this.
        max_s: Hard ceiling; a segment never exceeds it unless it is a single sentence.
        min_s: A trailing remainder shorter than this merges into the previous segment.

    Returns:
        Segment drafts with non-overlapping spans that tile the sentences in order.

    Notes:
        A sentence is never split, so a single sentence longer than ``max_s`` becomes its own
        segment — an oversized segment is preferable to a fragment with no proposition in it.
    """
    if not sentences:
        return ()

    groups: list[list[Sentence]] = []
    current: list[Sentence] = []

    for sentence in sentences:
        if current:
            prospective_span = sentence.end_s - current[0].start_s
            reached_target = current[-1].end_s - current[0].start_s >= target_s
            if prospective_span > max_s or reached_target:
                groups.append(current)
                current = []
        current.append(sentence)

    if current:
        groups.append(current)

    if len(groups) > 1:
        last = groups[-1]
        last_span = last[-1].end_s - last[0].start_s
        merged_span = last[-1].end_s - groups[-2][0].start_s
        if last_span < min_s and merged_span <= max_s:
            groups[-2].extend(groups.pop())

    return tuple(_draft(video_id, group) for group in groups)


def segment_by_pause(
    sentences: Sequence[Sentence],
    video_id: str,
    *,
    pause_s: float = PAUSE_S,
    min_s: float = PAUSE_MIN_S,
    target_s: float = PAUSE_TARGET_S,
    max_s: float = PAUSE_MAX_S,
) -> tuple[SegmentDraft, ...]:
    """Group sentences into segments, cutting at pauses in speech.

    Args:
        sentences: Time-ordered sentences for one video.
        video_id: Owning video id, used to build deterministic segment ids.
        pause_s: Silence between two sentences that counts as a boundary.
        min_s: A shorter segment is merged into its neighbour when that stays under ``max_s``.
        target_s: Once a segment reaches this length, the next sentence starts a new one regardless.
        max_s: Hard ceiling.

    Returns:
        Segment drafts with non-overlapping spans that tile the sentences in order.

    Notes:
        A pause only closes a segment once it is at least ``min_s`` long, so a single loud silence
        does not produce a two-second fragment. The duration bounds exist because a pause-aware rule
        alone yields segments of wildly varying length — a monologue with no pauses would become one
        enormous chunk and
        never reach the topic model as a unit of comparable size.
    """
    if not sentences:
        return ()

    groups: list[list[Sentence]] = []
    current: list[Sentence] = []

    for sentence in sentences:
        if current:
            gap = sentence.start_s - current[-1].end_s
            span = current[-1].end_s - current[0].start_s
            prospective = sentence.end_s - current[0].start_s
            pause_boundary = gap >= pause_s and span >= min_s
            if pause_boundary or span >= target_s or prospective > max_s:
                groups.append(current)
                current = []
        current.append(sentence)

    if current:
        groups.append(current)

    groups = _merge_short_groups(groups, min_s=min_s, max_s=max_s)
    return tuple(_draft(video_id, group) for group in groups)


def segment_by_drift(
    sentences: Sequence[Sentence],
    similarities: Sequence[float],
    video_id: str,
    *,
    threshold: float,
    min_s: float = PAUSE_MIN_S,
    target_s: float = PAUSE_TARGET_S,
    max_s: float = PAUSE_MAX_S,
) -> tuple[SegmentDraft, ...]:
    """Group sentences, cutting where similarity to the next sentence drops below a threshold.

    Args:
        sentences: Time-ordered sentences for one video.
        similarities: ``similarities[i]`` is the semantic similarity of sentence ``i`` to ``i + 1``;
            length must be ``len(sentences) - 1``.
        video_id: Owning video id, used to build deterministic segment ids.
        threshold: Similarity below which a boundary is placed, computed by the caller from the
            video's own distribution.
        min_s: Minimum segment length before a drop may cut.
        target_s: Length at which a segment closes regardless.
        max_s: Hard ceiling.

    Returns:
        Segment drafts tiling the sentences in order.

    Raises:
        ValueError: If ``similarities`` is not aligned with the sentence pairs.

    Notes:
        Measured on 20 videos (2026-11-14): drift boundaries separate topics far better than
        time-based ones — mean similarity across a boundary 0.2792 against 0.4626 inside a segment
        (gap **+0.217**), where fixed windows produced gap -0.015 and pauses -0.015. That is the
        reason this method exists and the others are kept only as controls.

        The threshold is supplied rather than computed here because the domain must stay pure: the
        caller derives it from the video's own similarity distribution, since a flat bulletin and a
        heated interview have different scales.
    """
    if not sentences:
        return ()
    if len(similarities) != len(sentences) - 1:
        raise ValueError(
            f"need {len(sentences) - 1} similarities for {len(sentences)} sentences, "
            f"got {len(similarities)}"
        )

    groups: list[list[Sentence]] = []
    current: list[Sentence] = []

    for position, sentence in enumerate(sentences):
        if current:
            span = current[-1].end_s - current[0].start_s
            prospective = sentence.end_s - current[0].start_s
            drop = similarities[position - 1] < threshold
            if (drop and span >= min_s) or span >= target_s or prospective > max_s:
                groups.append(current)
                current = []
        current.append(sentence)

    if current:
        groups.append(current)

    groups = _merge_short_groups(groups, min_s=min_s, max_s=max_s)
    return tuple(_draft(video_id, group, prefix="drift:") for group in groups)


def _merge_short_groups(
    groups: list[list[Sentence]], *, min_s: float, max_s: float
) -> list[list[Sentence]]:
    """Fold segments shorter than ``min_s`` into a neighbour.

    Args:
        groups: Segments in order.
        min_s: Minimum acceptable span.
        max_s: Hard ceiling on the merged span.

    Returns:
        The groups, with short ones absorbed where the result still respects ``max_s``.

    Notes:
        Merging forward first keeps the earlier segment's boundary, which is the one that came from
        pause in speech — absorbing backwards would move a boundary that the audio justifies.
    """
    merged: list[list[Sentence]] = []
    for group in groups:
        span = group[-1].end_s - group[0].start_s
        if merged and span < min_s and (group[-1].end_s - merged[-1][0].start_s) <= max_s:
            merged[-1].extend(group)
            continue
        merged.append(list(group))

    if len(merged) > 1:
        last = merged[-1]
        last_span = last[-1].end_s - last[0].start_s
        if last_span < min_s and (last[-1].end_s - merged[-2][0].start_s) <= max_s:
            merged[-2].extend(merged.pop())
    return merged
