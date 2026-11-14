"""Humanise topic labels through the LLM gateway (SPEC-007 increment).

SPEC-007 shipped keyword labels because the gateway did not exist. It does now (SPEC-005), and
Gemini's free tier makes thirty calls cost nothing, so a topic can carry a real name in two
languages instead of its top keyword.

The outlier bucket is never labelled: "unclassified" is a statement about coverage, not a topic, and
giving it a name would invite it onto a chart as if it were one.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from gtaf.domain.topics import OUTLIER_TOPIC_ID

LABEL_PROMPT_VERSION = "topic-label-v1"
MAX_KEYWORDS = 12


class LabelGateway(Protocol):
    """Subset of the LLM gateway this use case needs."""

    def ask(self, prompt: str, *, prompt_version: str, provider: str) -> object:
        """Return a response with a ``text`` attribute."""
        ...


class TopicLabelRepository(Protocol):
    """Persistence for topic labels."""

    def latest_topics_run(self) -> str | None:
        """Return the newest run that has topics, or None."""
        ...

    def list_topics(self, run_id: str) -> tuple[tuple[int, str | None, tuple[str, ...], int], ...]:
        """Return ``(topic_id, label_ka, keywords, n_segments)`` rows."""
        ...

    def update_topic_labels(
        self, run_id: str, labels: Mapping[int, tuple[str, str | None]]
    ) -> int:
        """Write labels for a run and return the number of rows updated."""
        ...


@dataclass(frozen=True, slots=True)
class LabelResult:
    """Outcome of a labelling pass.

    Attributes:
        run_id: Topics run that was labelled.
        labelled: Topics that received an LLM label.
        skipped: Topics left with their keyword label (outliers, or an unusable answer).
    """

    run_id: str
    labelled: int
    skipped: int


def build_prompt(keywords: Sequence[str], n_segments: int) -> str:
    """Render the labelling prompt for one topic.

    Args:
        keywords: The cluster's top terms, already free of stopwords.
        n_segments: Cluster size, which helps the model judge specificity.

    Returns:
        A Georgian instruction requesting strict JSON.

    Notes:
        Asking for both languages in one call halves the quota cost of a bilingual corpus, and
        JSON-only keeps the parse trivial — a model that adds prose is a model whose answer cannot
        be stored.
    """
    terms = ", ".join(keywords[:MAX_KEYWORDS])
    return (
        "ქვემოთ მოცემულია ქართული ტელევიზიის სიუჟეტების კლასტერის საკვანძო სიტყვები. "
        "შეადგინე თემის ზუსტი, კონკრეტული სახელწოდება ქართულად (2-5 სიტყვა) და ინგლისურად "
        "(2-5 words). არ დაწერო ზოგადი სიტყვები როგორიცაა 'სიახლეები' ან 'პოლიტიკა'.\n"
        'უპასუხე მხოლოდ JSON-ით: {"label_ka": "...", "label_en": "..."}\n\n'
        f"საკვანძო სიტყვები: {terms}\n"
        f"კლასტერის ზომა: {n_segments} სეგმენტი"
    )


def parse_label(text: str) -> tuple[str, str | None] | None:
    """Parse a model reply into a Georgian and an English label.

    Args:
        text: Raw reply, possibly wrapped in a markdown code fence.

    Returns:
        ``(label_ka, label_en)``, or None when the reply is not usable JSON with a Georgian label.

    Notes:
        A reply that cannot be parsed is not repaired by guessing: the topic keeps its keyword
        label, which is honest, rather than receiving a name the model did not propose.    """
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[1] if "```" in cleaned[3:] else cleaned[3:]
        cleaned = cleaned.removeprefix("json").strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    label_ka = str(data.get("label_ka") or "").strip()
    if not label_ka:
        return None
    label_en = str(data.get("label_en") or "").strip() or None
    return label_ka, label_en


def label_topics(
    gateway: LabelGateway,
    repo: TopicLabelRepository,
    *,
    provider: str,
    run_id: str | None = None,
) -> LabelResult:
    """Label every real topic of a run through the gateway.

    Args:
        gateway: LLM gateway.
        repo: Topic persistence.
        provider: Provider key to call.
        run_id: Run to label, defaulting to the newest one with topics.

    Returns:
        Counts of labelled and skipped topics.

    Raises:
        ValueError: If there is no topics run to label.
    """
    target = run_id or repo.latest_topics_run()
    if target is None:
        raise ValueError("no topics run found; run `gtaf topics` first")

    labels: dict[int, tuple[str, str | None]] = {}
    skipped = 0
    for topic_id, _current, keywords, n_segments in repo.list_topics(target):
        if topic_id == OUTLIER_TOPIC_ID or not keywords:
            skipped += 1
            continue
        response = gateway.ask(
            build_prompt(keywords, n_segments),
            prompt_version=LABEL_PROMPT_VERSION,
            provider=provider,
        )
        parsed = parse_label(str(getattr(response, "text", "")))
        if parsed is None:
            skipped += 1
            continue
        labels[topic_id] = parsed

    repo.update_topic_labels(target, labels)
    return LabelResult(run_id=target, labelled=len(labels), skipped=skipped)
