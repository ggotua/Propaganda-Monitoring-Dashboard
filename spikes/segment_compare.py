"""Compare three segmentation rules on the real corpus (SPEC-006).

The question is not "which produces fewer segments" — it is whether a boundary lands where the argument
changes. That is measured as the **gap** between mean similarity inside a segment and mean similarity
across a boundary: a good segmenter puts like with like and changes of subject on the boundary.

Reported per method: segment count, duration distribution, share of very short segments, intra and inter
similarity, and their gap.

Result on 20 videos (2026-11-14):

    method  segments  median_s   intra   inter     gap
    fixed        190      96.3  0.4626  0.4776 -0.0150
    pause        281      64.7  0.4619  0.4767 -0.0148
    drift        282      52.1  0.4961  0.2792 +0.2169

Drift — cutting where similarity to the next sentence drops — is the only rule whose boundaries separate
topics. The other two are kept as controls.

Run: python spikes/segment_compare.py [--videos N]
"""

from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gtaf.application.text import sentences_for_video
from gtaf.domain.segment import segment_by_pause, segment_sentences
from gtaf.infrastructure.db import connect
from gtaf.infrastructure.repository import DuckDBRepository

MODEL_NAME = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"


def _cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity of two vectors."""
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm = (sum(x * x for x in a) ** 0.5) * (sum(y * y for y in b) ** 0.5)
    return dot / norm if norm else 0.0


def _sim(text_a: str, text_b: str, vectors: dict[str, list[float]]) -> float | None:
    """Similarity of two sentences, or None when one is missing."""
    a = vectors.get(text_a)
    b = vectors.get(text_b)
    if a is None or b is None:
        return None
    return _cosine(a, b)


def discriminate(
    segments: list[tuple[str, ...]], vectors: dict[str, list[float]]
) -> tuple[float, float, float]:
    """Return (intra, inter, gap) similarities.

    Args:
        segments: Segments as ordered sentence texts.
        vectors: Sentence text to embedding.

    Returns:
        ``(intra, inter, gap)`` where ``intra`` is the mean similarity of adjacent sentences *inside*
        a segment, ``inter`` is the mean similarity of the last sentence of one segment to the first of
        the next, and ``gap = intra - inter``.

    Notes:
        A segmenter earns its keep by making the gap large: it should put similar sentences together and
        put changes of subject on the boundary. Cohesion alone cannot show this — it rises simply by
        making segments shorter, which is why the first version of this comparison was uninformative.
    """
    intra_total, intra_pairs = 0.0, 0
    inter_total, inter_pairs = 0.0, 0
    for segment in segments:
        for left, right in zip(segment, segment[1:], strict=False):
            value = _sim(left, right, vectors)
            if value is not None:
                intra_total += value
                intra_pairs += 1
    for current, following in zip(segments, segments[1:], strict=False):
        if not current or not following:
            continue
        value = _sim(current[-1], following[0], vectors)
        if value is not None:
            inter_total += value
            inter_pairs += 1
    intra = intra_total / intra_pairs if intra_pairs else 0.0
    inter = inter_total / inter_pairs if inter_pairs else 0.0
    return intra, inter, intra - inter


def cohesion(segments: list[tuple[str, ...]], vectors: dict[str, list[float]]) -> float:
    """Mean cosine similarity of consecutive sentences within segments."""
    return discriminate(segments, vectors)[0]


def drift_groups(
    sentences: list[tuple[float, float, str]],
    vectors: dict[str, list[float]],
    *,
    min_s: float = 20.0,
    max_s: float = 150.0,
    quantile: float = 0.25,
) -> list[tuple[str, ...]]:
    """Split sentences where semantic similarity between neighbours drops.

    Args:
        sentences: ``(start_s, end_s, text)`` in order.
        vectors: Sentence text to embedding.
        min_s: Do not cut before this many seconds.
        max_s: Force a cut at this length.
        quantile: Similarities below this per-video quantile count as a drop.

    Returns:
        Groups of sentence texts.

    Notes:
        The threshold is per video, not global: a bulletin spoken in flat register has a different
        similarity distribution than a heated interview, and a global cut-off would shatter one and
        merge the other.
    """
    if not sentences:
        return []
    sims: list[float | None] = []
    for (_, _, left), (_, _, right) in zip(sentences, sentences[1:], strict=False):
        sims.append(_sim(left, right, vectors))
    known = [value for value in sims if value is not None]
    if not known:
        return [tuple(text for _, _, text in sentences)]
    ordered = sorted(known)
    index = min(len(ordered) - 1, max(0, int(quantile * len(ordered))))
    threshold = ordered[index]

    groups: list[tuple[str, ...]] = []
    current: list[tuple[float, float, str]] = []
    for position, sentence in enumerate(sentences):
        if current:
            span = current[-1][1] - current[0][0]
            prospective = sentence[1] - current[0][0]
            drop = position - 1 < len(sims) and sims[position - 1] is not None
            is_drop = drop and sims[position - 1] is not None and sims[position - 1] < threshold
            if (is_drop and span >= min_s) or span >= max_s or prospective > max_s * 1.5:
                groups.append(tuple(text for _, _, text in current))
                current = []
        current.append(sentence)
    if current:
        groups.append(tuple(text for _, _, text in current))
    return groups


def main() -> int:
    """Run the comparison and print a table."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--videos", type=int, default=20)
    args = parser.parse_args()

    conn = connect(Path("data/gtaf.duckdb"), read_only=True)
    repo = DuckDBRepository(conn)
    video_ids = repo.list_video_ids()[: args.videos]
    print(f"comparing on {len(video_ids)} videos")

    per_method: dict[str, dict[str, object]] = {
        "fixed": {"segments": [], "texts": []},
        "pause": {"segments": [], "texts": []},
        "drift": {"segments": [], "texts": []},
    }
    all_texts: set[str] = set()
    per_video_sentences: list[list[tuple[float, float, str]]] = []
    per_video_id: list[str] = []

    for index, video_id in enumerate(video_ids, start=1):
        result = sentences_for_video(video_id, repo)
        sentences = result.sentences
        if not sentences:
            continue
        per_video_sentences.append([(s.start_s, s.end_s, s.text) for s in sentences])
        per_video_id.append(video_id)
        all_texts.update(s.text for s in sentences)

        fixed = segment_sentences(sentences, video_id)
        paused = segment_by_pause(sentences, video_id)
        for name, drafts in (("fixed", fixed), ("pause", paused)):
            per_method[name]["segments"].extend((d.start_s, d.end_s) for d in drafts)  # type: ignore[union-attr]
            groups: list[tuple[str, ...]] = []
            for draft in drafts:
                groups.append(
                    tuple(
                        s.text
                        for s in sentences
                        if s.start_s >= draft.start_s - 0.001
                        and s.end_s <= draft.end_s + 0.001
                    )
                )
            per_method[name]["texts"].extend(groups)  # type: ignore[union-attr]
        if index % 5 == 0:
            print(f"  {index}/{len(video_ids)} videos prepared")

    conn.close()

    print(f"embedding {len(all_texts)} unique sentences with {MODEL_NAME}")
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(MODEL_NAME)
    texts = sorted(all_texts)
    embeddings = model.encode(texts, batch_size=64, show_progress_bar=False)
    vectors = {text: embeddings[i].tolist() for i, text in enumerate(texts)}

    for sentences_with_spans in per_video_sentences:
        groups = drift_groups(sentences_with_spans, vectors)
        per_method["drift"]["texts"].extend(groups)  # type: ignore[union-attr]
        for group in groups:
            spans = [
                (start, end)
                for start, end, text in sentences_with_spans
                if any(text == member for member in group)
            ]
            if spans:
                per_method["drift"]["segments"].append(  # type: ignore[union-attr]
                    (min(s for s, _ in spans), max(e for _, e in spans))
                )

    print(
        f"\n{'method':8} {'segments':>9} {'median_s':>9} {'mean_s':>8} {'short%':>7} "
        f"{'intra':>7} {'inter':>7} {'gap':>7}"
    )
    for name in ("fixed", "pause", "drift"):
        spans = per_method[name]["segments"]
        groups = per_method[name]["texts"]
        durations = [end - start for start, end in spans]  # type: ignore[misc]
        short = sum(1 for d in durations if d < 15) / len(durations) if durations else 0
        intra, inter, gap = discriminate(groups, vectors)  # type: ignore[arg-type]
        print(
            f"{name:8} {len(spans):>9} {statistics.median(durations):>9.1f} "
            f"{statistics.mean(durations):>8.1f} {short:>6.1%} "
            f"{intra:>7.4f} {inter:>7.4f} {gap:>7.4f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
