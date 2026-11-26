"""Web ingestion use case (SPEC-018).

Turns a configured source into stored publications: discover, respect robots, fetch, extract, persist. The
discovery mechanism varies by source (RSS, sitemap, listing), which is why the source row carries both a kind
and a listing URL.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Protocol

from gtaf.domain.web import (
    RawItem,
    WebSource,
    body_fingerprint,
    dedupe_by_title,
    extract_excerpt,
    looks_like_article,
    newest_first,
    parse_listing,
    parse_rss,
    parse_sitemap,
    parse_sitemap_dates,
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

    def set_publication_date(self, publication_id: str, published_at: datetime) -> int:
        """Write a publication's timestamp; returns rows written."""
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


def backfill_dates(source: WebSource, fetcher: Fetcher, store: PublicationStore) -> int:
    """Fill missing publication dates from the source sitemap.

    Args:
        source: Configured source with a sitemap.
        fetcher: Page fetcher.
        store: Publication persistence.

    Returns:
        Number of dates written.

    Notes:
        One request per source. The alternative — re-fetching every article — is what a sitemap exists to
        avoid.
    """
    if not source.sitemap_url or not fetcher.allowed(source.sitemap_url):
        return 0
    body = fetcher.get(source.sitemap_url, timeout=60)
    dates = parse_sitemap_dates(body)
    written = 0
    for url, published_at in dates.items():
        if published_at is None or not looks_like_article(url):
            continue
        written += store.set_publication_date(
            publication_id(source.source_id, url), published_at
        )
    return written


def discover(
    source: WebSource,
    fetcher: Fetcher,
    *,
    limit: int,
    sitemap: bool = False,
    start: date | None = None,
    end: date | None = None,
) -> tuple[RawItem, ...]:
    """Find candidate publications for a source.

    Args:
        source: Configured source.
        fetcher: Page fetcher.
        limit: Maximum items.
        sitemap: Use the source's sitemap for a backfill instead of its listing page.
        start: First day to include, when filtering a sitemap backfill by ``lastmod``.
        end: Last day to include.

    Returns:
        Items, de-duplicated by title.

    Notes:
        The window filter exists because a concordance needs articles from the same days as the broadcast
        corpus: measured 2026-11-26, the newest 400 Imedi articles were all from 24 to 26 November, leaving the
        3 to 13 November broadcast window with zero web publications to compare against.
    """
    if sitemap and source.sitemap_url:
        if not fetcher.allowed(source.sitemap_url):
            return ()
        body = fetcher.get(source.sitemap_url, timeout=60)
        dates = parse_sitemap_dates(body)
        wanted = [
            url
            for url, published_at in dates.items()
            if looks_like_article(url)
            and (
                start is None
                or end is None
                or (
                    published_at is not None
                    and start <= published_at.date() <= end
                )
            )
        ]
        chosen = newest_first(wanted, limit=limit)
        return tuple(
            RawItem(url=url, title="", published_at=dates.get(url)) for url in chosen
        )

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
    sitemap: bool = False,
    start: date | None = None,
    end: date | None = None,
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
    items = discover(source, fetcher, limit=limit, sitemap=sitemap, start=start, end=end)

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
    sitemap: bool = False,
    start: date | None = None,
    end: date | None = None,
) -> tuple[IngestResult, ...]:
    """Ingest every active source.

    Args:
        sources: Sources to process.
        fetcher: Page fetcher.
        store: Publication persistence.
        limit: Maximum publications per source.
        sitemap: Backfill from each source's sitemap.
        start: First day to include, for a windowed sitemap backfill.
        end: Last day to include.

    Returns:
        One result per source.
    """
    return tuple(
        ingest_source(
            source, fetcher, store, limit=limit, sitemap=sitemap, start=start, end=end
        )
        for source in sources
    )
