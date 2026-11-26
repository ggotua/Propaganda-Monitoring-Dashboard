"""Web ingestion use case (SPEC-018).

Turns a configured source into stored publications: discover, respect robots, fetch, extract, persist. The
discovery mechanism varies by source (RSS, sitemap, listing), which is why the source row carries both a kind
and a listing URL.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from gtaf.domain.web import (
    RawItem,
    WebSource,
    body_fingerprint,
    dedupe_by_title,
    extract_excerpt,
    looks_like_article,
    parse_listing,
    parse_rss,
    parse_sitemap,
    publication_id,
)


class Source(Protocol):
    """A configured web source."""

    source_id: str
    leaning: str
    base_url: str
    access_mode: str
    kind: str
    listing_url: str


class Fetcher(Protocol):
    """Page fetcher with a robots policy."""

    def get(self, url: str, *, timeout: int = 30) -> str:
        """Fetch a URL."""
        ...

    def allowed(self, url: str) -> bool:
        """Return whether robots.txt permits the URL."""
        ...


class PublicationStore(Protocol):
    """Persistence for publications."""

    def upsert_publication(self, row: tuple[object, ...]) -> int:
        """Insert or update one publication; returns rows written."""
        ...


@dataclass(frozen=True, slots=True)
class IngestResult:
    """Outcome of one source's ingest.

    Attributes:
        source_id: Source processed.
        discovered: Items found by the discovery step.
        stored: Publications written (new or updated).
        blocked_by_robots: URLs skipped because robots.txt disallowed them.
        failed: Pages that could not be fetched.
        with_text: Publications whose body text was retrieved.
    """

    source_id: str
    discovered: int
    stored: int
    blocked_by_robots: int
    failed: int
    with_text: int


def discover(source: WebSource, fetcher: Fetcher, *, limit: int) -> tuple[RawItem, ...]:
    """Find candidate publications for a source.

    Args:
        source: Configured source.
        fetcher: Page fetcher.
        limit: Maximum items.

    Returns:
        Items, de-duplicated by title.

    Notes:
        The sitemap path exists because one source's listing is JavaScript-driven: scraping the listing would
        yield an empty shell and a nightly "0 articles" that looks like an outage.
    """
    if not fetcher.allowed(source.listing_url):
        return ()

    body = fetcher.get(source.listing_url)
    if source.kind == "rss":
        items = parse_rss(body)
    elif source.kind == "sitemap":
        pattern = r"/ka/siaxleebi/"
        urls = parse_sitemap(body, base_url=source.base_url, pattern=pattern)
        items = tuple(RawItem(url=url, title="") for url in urls)
    else:
        items = parse_listing(
            body, base_url=source.base_url, link_pattern=r"/ka/siaxleebi/|/ge/"
        )
    # A listing also links to sibling sections; only article URLs are publications.
    items = tuple(item for item in items if looks_like_article(item.url))
    return dedupe_by_title(items)[:limit]


def ingest_source(
    source: WebSource,
    fetcher: Fetcher,
    store: PublicationStore,
    *,
    limit: int = 20,
    now: datetime | None = None,
) -> IngestResult:
    """Ingest one source.

    Args:
        source: Configured source.
        fetcher: Page fetcher.
        store: Publication persistence.
        limit: Maximum publications to process.
        now: Fetch timestamp, injectable for tests.

    Returns:
        Counts for the run.

    Notes:
        When a source is configured ``headline``, its article pages are never requested — the access mode is a
        permission decision recorded in the database, not a performance tweak.
    """
    moment = now or datetime.now(UTC).replace(tzinfo=None)
    items = discover(source, fetcher, limit=limit)

    stored = 0
    blocked = 0
    failed = 0
    with_text = 0

    for item in items:
        title = item.title
        excerpt = ""
        digest: str | None = None
        chars = 0

        if source.access_mode != "headline":
            if not fetcher.allowed(item.url):
                blocked += 1
                continue
            try:
                page = fetcher.get(item.url)
            except Exception:  # noqa: BLE001 - one dead page must not sink the run
                failed += 1
                continue
            excerpt = extract_excerpt(page)
            if excerpt:
                digest = body_fingerprint(excerpt)
                chars = len(excerpt)
                with_text += 1
            if not title:
                title = _title_from_page(page, fallback=item.url)

        created = store.upsert_publication(
            (
                publication_id(source.source_id, item.url),
                source.source_id,
                item.url,
                title,
                item.published_at,
                item.programme,
                excerpt,
                digest,
                chars,
                moment,
            )
        )
        stored += created

    return IngestResult(
        source_id=source.source_id,
        discovered=len(items),
        stored=stored,
        blocked_by_robots=blocked,
        failed=failed,
        with_text=with_text,
    )


def _title_from_page(page: str, *, fallback: str) -> str:
    """Extract a headline from a page that had no listing title.

    Args:
        page: Article HTML.
        fallback: Value used when nothing better is found.

    Returns:
        A headline, or the fallback URL.
    """
    import re

    for pattern in (r"<h1[^>]*>(.*?)</h1>", r"<title[^>]*>(.*?)</title>"):
        match = re.search(pattern, page, re.DOTALL)
        if match:
            text = " ".join(re.sub(r"<[^>]+>", " ", match.group(1)).split())
            if text:
                return text[:300]
    return fallback


def ingest_all(
    sources: Sequence[WebSource],
    fetcher: Fetcher,
    store: PublicationStore,
    *,
    limit: int = 20,
) -> tuple[IngestResult, ...]:
    """Ingest every active source.

    Args:
        sources: Sources to process.
        fetcher: Page fetcher.
        store: Publication persistence.
        limit: Maximum publications per source.

    Returns:
        One result per source.
    """
    return tuple(
        ingest_source(source, fetcher, store, limit=limit) for source in sources
    )
