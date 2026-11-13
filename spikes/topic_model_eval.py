"""Topic-model evaluation: two embedding models on the same segments (SPEC-007 §2).

Runs BERTopic twice with identical parameters and reports the numbers the spec says decide the
choice: topic count, outlier rate (primary criterion), embedding wall time, and the top terms of the
largest topics so a human can judge whether they describe subjects or formats.

Reads the database read-only; writes nothing. Run with an empty database open (collection locks it).
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("HF_HOME", str(Path(__file__).resolve().parents[1] / ".hf-cache"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import duckdb
from bertopic import BERTopic
from hdbscan import HDBSCAN
from sklearn.feature_extraction.text import CountVectorizer
from umap import UMAP

from gtaf.domain.topics import GEORGIAN_STOPWORDS

DB = "data/gtaf.duckdb"
SAMPLE = 600
MIN_TOPIC_SIZE = 15
RANDOM_STATE = 42
MAX_DF = 0.4
MODELS = (
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    "sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
)


def load_sample() -> list[str]:
    """Return a deterministic sample of segment texts.

    Returns:
        Up to ``SAMPLE`` segment texts in a fixed order.
    """
    conn = duckdb.connect(DB, read_only=True)
    try:
        rows = conn.execute(
            "SELECT text FROM segments ORDER BY segment_id LIMIT ?", [SAMPLE]
        ).fetchall()
    finally:
        conn.close()
    return [str(row[0]) for row in rows]


def evaluate(model_name: str, docs: list[str]) -> dict[str, object]:
    """Fit BERTopic with one embedding model and report its metrics.

    Args:
        model_name: Sentence-transformers model id.
        docs: Segment texts.

    Returns:
        A dict of metrics plus the largest topics' top terms.
    """
    vectorizer = CountVectorizer(
        ngram_range=(1, 2),
        min_df=3,
        max_df=MAX_DF,
        stop_words=list(GEORGIAN_STOPWORDS),
    )
    started = time.perf_counter()
    # BERTopic 0.17 takes no `random_state`; determinism comes from the UMAP and HDBSCAN models,
    # which must be supplied explicitly (SPEC-007 FR-3).
    umap_model = UMAP(
        n_neighbors=15,
        n_components=5,
        min_dist=0.0,
        metric="cosine",
        random_state=RANDOM_STATE,
    )
    hdbscan_model = HDBSCAN(
        min_cluster_size=MIN_TOPIC_SIZE,
        metric="euclidean",
        cluster_selection_method="eom",
        prediction_data=True,
    )
    topic_model = BERTopic(
        embedding_model=model_name,
        umap_model=umap_model,
        hdbscan_model=hdbscan_model,
        calculate_probabilities=False,
        verbose=False,
        vectorizer_model=vectorizer,
    )
    topics, _ = topic_model.fit_transform(docs)
    elapsed = time.perf_counter() - started

    n_topics = len({topic for topic in topics if topic != -1})
    n_outliers = sum(1 for topic in topics if topic == -1)
    info = topic_model.get_topic_info()
    sizes = [int(row) for row in info.loc[info["Topic"] != -1, "Count"].tolist()]

    top_terms: list[dict[str, object]] = []
    for topic_id in sorted({t for t in topics if t != -1})[:5]:
        words = topic_model.get_topic(topic_id) or []
        top_terms.append(
            {
                "topic": int(topic_id),
                "size": int(next(iter(info.loc[info["Topic"] == topic_id, "Count"].tolist()), 0)),
                "terms": [str(word) for word, _ in words[:6]],
            }
        )

    return {
        "model": model_name,
        "documents": len(docs),
        "topics": n_topics,
        "outlier_rate": round(n_outliers / len(docs), 4) if docs else 0.0,
        "median_topic_size": sorted(sizes)[len(sizes) // 2] if sizes else 0,
        "largest_topic": max(sizes) if sizes else 0,
        "seconds": round(elapsed, 1),
        "top_terms": top_terms,
    }


def main() -> int:
    """Evaluate every candidate model and print a comparison.

    Returns:
        Process exit code (always 0 unless the sample is empty).
    """
    docs = load_sample()
    print(f"sample: {len(docs)} segments")
    if not docs:
        print("no segments to evaluate")
        return 1

    results = [evaluate(model, docs) for model in MODELS]
    print("\n| model | topics | outlier rate | median size | largest | seconds |")
    print("|---|---|---|---|---|---|")
    for result in results:
        print(
            f"| {result['model'].split('/')[-1]} | {result['topics']} | "
            f"{result['outlier_rate']:.1%} | {result['median_topic_size']} | "
            f"{result['largest_topic']} | {result['seconds']} |"
        )
    print()
    for result in results:
        print(f"--- {result['model'].split('/')[-1]} top topics ---")
        for entry in result["top_terms"]:
            print(f"  t{entry['topic']} (n={entry['size']}): {', '.join(entry['terms'])}")

    Path(".tmp").mkdir(exist_ok=True)
    Path(".tmp/topic_eval.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("\nwrote .tmp/topic_eval.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
