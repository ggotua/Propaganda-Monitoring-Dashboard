"""Local sentence embeddings adapter (SPEC-006).

The drift segmenter needs to know when the text stops being about the same thing, which requires
similarity between neighbouring sentences. Embeddings are computed **locally** — the same
multilingual model the topic stage uses — so segmentation costs no API calls and no quota (D-026).

The model is loaded once per process: loading it costs seconds, and a per-video reload would
dominate a corpus-wide run.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol

DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"


class Embedder(Protocol):
    """Turns texts into vectors."""

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed a batch of texts.

        Args:
            texts: Texts to embed, in order.

        Returns:
            One vector per text.
        """
        ...


class SentenceTransformerEmbedder:
    """SentenceTransformer-backed embedder with a lazily loaded model."""

    def __init__(self, model_name: str = DEFAULT_MODEL) -> None:
        """Store the model name; the model itself loads on first use.

        Args:
            model_name: HuggingFace model id.
        """
        self._model_name = model_name
        self._model: Any = None

    def _load(self) -> Any:
        """Load the model once."""
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self._model_name)
        return self._model

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed texts.

        Args:
            texts: Texts to embed.

        Returns:
            Vectors as plain lists, so nothing downstream depends on numpy.
        """
        if not texts:
            return []
        vectors = self._load().encode(
            list(texts), batch_size=64, show_progress_bar=False, normalize_embeddings=False
        )
        return [vector.tolist() for vector in vectors]


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity of two vectors.

    Args:
        a: First vector.
        b: Second vector.

    Returns:
        Similarity in ``[-1, 1]``, or 0 when either vector has zero length.
    """
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0
