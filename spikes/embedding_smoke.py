"""Smoke-test that the embedding chain actually embeds Georgian (D-007 follow-through).

Imports prove installation, not usefulness. This loads a small multilingual model once, embeds a few
real segments, and checks the embeddings are discriminative: similar sentences closer than unrelated
ones. It does not choose the production model (that is SPEC-006/007) — it answers one question: does
this stack produce meaningful vectors for Georgian text on this interpreter?
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# HuggingFace defaults to %USERPROFILE%\.cache\huggingface, which this machine refuses to create
# (WinError 5). Point the cache inside the workspace so the download is reproducible and the model
# files are discoverable rather than hidden in a user profile.
os.environ.setdefault("HF_HOME", str(Path(__file__).resolve().parents[1] / ".hf-cache"))

# Must follow the HF_HOME assignment: the import resolves its cache directory at import time.
from sentence_transformers import SentenceTransformer

MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

# Deliberately taken from the collected corpus register: two about the EU summit, one about a gas
# inspection, so "similar" and "unrelated" are separable by meaning rather than vocabulary.
SENTENCES = [
    "ევროპელი ლიდერები დუბლინში სამიტზე იკრიბებიან და გაფართოებაზე იმსჯელებენ.",
    "ევროპული პოლიტიკური გაერთიანების სამიტი დუბლინში იხსნება, ლიდერები უსაფრთხოებაზე საუბრობენ.",
    "გაზის დანადგარების გეგმიური შემოწმება ნაძალადევის რაიონში ჩატარდა.",
]


def main() -> int:
    """Embed the sentences and report similarity structure.

    Returns:
        Process exit code: 0 when embeddings are discriminative, 1 otherwise.
    """
    model = SentenceTransformer(MODEL)
    vectors = model.encode(SENTENCES, normalize_embeddings=True)

    print(f"model      : {MODEL}")
    print(f"dimensions : {vectors.shape[1]}")
    print(f"dtype      : {vectors.dtype}")
    print(f"norm(0)    : {float((vectors[0] ** 2).sum() ** 0.5):.4f}")

    related = float(vectors[0] @ vectors[1])
    unrelated_a = float(vectors[0] @ vectors[2])
    unrelated_b = float(vectors[1] @ vectors[2])
    print(f"similar   (0,1): {related:.4f}")
    print(f"unrelated (0,2): {unrelated_a:.4f}")
    print(f"unrelated (1,2): {unrelated_b:.4f}")

    discriminative = related > unrelated_a and related > unrelated_b
    print("VERDICT:", "GEORGIAN EMBEDDINGS WORK" if discriminative else "NOT DISCRIMINATIVE")
    return 0 if discriminative else 1


if __name__ == "__main__":
    sys.exit(main())
