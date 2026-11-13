"""BERTopic adapter (SPEC-007 §3).

The only module that imports the ML stack. Kept behind the `TopicEngine` protocol so the use case
and its tests never load a model.

Determinism: BERTopic 0.17 takes no `random_state`; randomness lives in UMAP and HDBSCAN, which are
supplied explicitly here with a fixed seed (FR-3).
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from gtaf.domain.topics import (
    GEORGIAN_STOPWORDS,
    OUTLIER_LABEL,
    OUTLIER_TOPIC_ID,
    TopicAssignment,
    TopicSummary,
)

DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"
DEFAULT_MIN_TOPIC_SIZE = 15
DEFAULT_RANDOM_STATE = 42

# HuggingFace writes to the user profile by default, which this machine refuses (WinError 5).
os.environ.setdefault("HF_HOME", str(Path(__file__).resolve().parents[3] / ".hf-cache"))


def _short_model_name(model_name: str) -> str:
    """Return the final path segment of a model id."""
    return model_name.rsplit("/", 1)[-1]


class BertopicEngine:
    """Topic engine backed by BERTopic over multilingual sentence embeddings."""

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        *,
        min_topic_size: int = DEFAULT_MIN_TOPIC_SIZE,
        random_state: int = DEFAULT_RANDOM_STATE,
    ) -> None:
        """Initialise the engine.

        Args:
            model_name: Sentence-transformers model id.
            min_topic_size: Smallest acceptable cluster; smaller clusters are outliers.
            random_state: Seed for UMAP, so repeated runs agree.
        """
        self.model_name = model_name
        self.min_topic_size = min_topic_size
        self.random_state = random_state

    @property
    def method_version(self) -> str:
        """Version string recorded on every assignment (D-009)."""
        return f"bertopic-{_short_model_name(self.model_name)}-1"

    def _build(self) -> Any:
        """Construct a BERTopic instance with deterministic components.

        Returns:
            A configured BERTopic model, typed loosely because the ML stack ships no annotations.
        """
        from bertopic import BERTopic
        from hdbscan import HDBSCAN
        from sklearn.feature_extraction.text import CountVectorizer

        # umap re-exports UMAP dynamically, so mypy cannot see the attribute; the library also has
        # no annotations, hence the untyped-call waiver below.
        from umap import UMAP  # type: ignore[attr-defined]

        umap_model = UMAP(  # type: ignore[no-untyped-call]
            n_neighbors=15,
            n_components=5,
            min_dist=0.0,
            metric="cosine",
            random_state=self.random_state,
        )
        return BERTopic(
            embedding_model=self.model_name,
            umap_model=umap_model,
            hdbscan_model=HDBSCAN(
                min_cluster_size=self.min_topic_size,
                metric="euclidean",
                cluster_selection_method="eom",
                prediction_data=True,
            ),
            calculate_probabilities=False,
            verbose=False,
            # Georgian stopwords and a document-frequency ceiling are both required: without them
            # every cluster's top terms were "და, რომ, ეს, არის" (D-020).
            vectorizer_model=CountVectorizer(
                ngram_range=(1, 2),
                min_df=3,
                max_df=0.4,
                stop_words=list(GEORGIAN_STOPWORDS),
            ),
        )

    def fit(
        self, segment_ids: Sequence[str], texts: Sequence[str]
    ) -> tuple[tuple[TopicAssignment, ...], tuple[TopicSummary, ...]]:
        """Cluster segment texts into topics.

        Args:
            segment_ids: Segment ids, parallel to ``texts``.
            texts: Segment texts.

        Returns:
            Assignments (one per segment, outliers as ``-1``) and one summary per topic.

        Notes:
            Labels are the top keyword, not a human phrase: the LLM gateway is SPEC-005 and does not
            exist yet, so a Georgian label here is a keyword by definition (SPEC-007 §1).
        """
        model = self._build()
        topics, _ = model.fit_transform(list(texts))

        counts: dict[int, int] = {}
        for topic_id in topics:
            counts[int(topic_id)] = counts.get(int(topic_id), 0) + 1

        summaries: list[TopicSummary] = []
        for topic_id in sorted(counts):
            if topic_id == OUTLIER_TOPIC_ID:
                summaries.append(
                    TopicSummary(
                        topic_id=OUTLIER_TOPIC_ID,
                        label_ka=OUTLIER_LABEL,
                        label_en=None,
                        keywords=(),
                        n_segments=counts[topic_id],
                    )
                )
                continue
            words = model.get_topic(topic_id) or []
            keywords = tuple(str(word) for word, _ in words[:10])
            summaries.append(
                TopicSummary(
                    topic_id=topic_id,
                    label_ka=keywords[0] if keywords else None,
                    label_en=None,
                    keywords=keywords,
                    n_segments=counts[topic_id],
                )
            )

        assignments = tuple(
            TopicAssignment(segment_id=segment_id, topic_id=int(topic_id))
            for segment_id, topic_id in zip(segment_ids, topics, strict=True)
        )
        return assignments, tuple(summaries)
