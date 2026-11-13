"""Fixed-window segmentation (SPEC-004).

Pure functions: sentences in, segment drafts out. This segmenter is deliberately disposable —
SPEC-006 replaces it — and its `seg_method` value exists so its output can never be mistaken for
real segmentation.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from gtaf.domain.normalise import Sentence

SEG_METHOD = "fixed"
SEG_VERSION = "1"

TARGET_S = 90.0
MAX_S = 240.0
MIN_S = 20.0


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


def _draft(video_id: str, group: Sequence[Sentence]) -> SegmentDraft:
    """Build a segment draft from a group of sentences.

    Args:
        video_id: Owning video.
        group: Consecutive sentences forming the segment.

    Returns:
        The draft, with a deterministic id derived from the start time in whole milliseconds so a
        re-run reproduces byte-identical ids.
    """
    start_s = group[0].start_s
    end_s = group[-1].end_s
    return SegmentDraft(
        segment_id=f"{video_id}:{round(start_s * 1000):08d}",
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
