"""Web publication parsing (SPEC-018).

Pure functions: raw bytes in, feed items out. No network here, so every parser is testable against a saved
fixture and a site redesign breaks a test rather than a nightly run.

Three discovery mechanisms are supported because the sources differ: RSS where a feed exists, a listing page
where it does not, and a sitemap where the listing is JavaScript-driven.
"""

from __future__ import annotations

import hashlib
import html
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urljoin

# Georgia is UTC+4 year-round (D-012); a listing timestamp is read as local and converted to UTC.
TBILISI = timedelta(hours=4)

KA_MONTHS = {
    "იანვარი": 1,
    "თებერვალი": 2,
    "მარტი": 3,
    "აპრილი": 4,
    "მაისი": 5,
    "ივნისი": 6,
    "ივლისი": 7,
    "აგვისტო": 8,
    "სექტემბერი": 9,
    "ოქტომბერი": 10,
    "ნოემბერი": 11,
    "დეკემბერი": 12,
}


@dataclass(frozen=True, slots=True)
class WebSource:
    """A configured web source.

    Attributes:
        source_id: Stable key.
        name_en: Display name.
        leaning: ``pro-government``, ``opposition`` or ``independent`` — an editorial judgement stored as data.
        base_url: Origin.
        access_mode: ``full``, ``headline`` or ``archive``; controls whether article pages are requested.
        kind: Discovery mechanism: ``rss``, ``listing`` or ``sitemap``.
        listing_url: Page or feed used for discovery.
        active: Whether the source takes part in a run.
        leaning_note: Who assigned the leaning and on what basis.
    """

    source_id: str
    name_en: str
    leaning: str
    base_url: str
    access_mode: str
    kind: str
    listing_url: str
    active: bool = True
    leaning_note: str | None = None
    sitemap_url: str | None = None


@dataclass(frozen=True, slots=True)
class RawItem:
    """One discovered publication before storage.

    Attributes:
        url: Absolute article URL.
        title: Headline.
        published_at: UTC timestamp when the listing provided one.
        programme: Programme label when the site exposes it.
    """

    url: str
    title: str
    published_at: datetime | None = None
    programme: str | None = None


def clean_text(value: str) -> str:
    """Collapse whitespace and decode entities in a scraped string.

    Args:
        value: Raw text, possibly with markup entities.

    Returns:
        Single-spaced, decoded text.
    """
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", value)).split())


def parse_iso(value: str) -> datetime | None:
    """Parse an RSS timestamp into a naive UTC datetime.

    Args:
        value: An RFC-822 or ISO-8601 timestamp.

    Returns:
        Naive UTC datetime, or None when unparseable.
    """
    cleaned = value.strip()
    for pattern in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            parsed = datetime.strptime(cleaned, pattern)
        except ValueError:
            continue
        if parsed.tzinfo is not None:
            return parsed.astimezone(UTC).replace(tzinfo=None)
        return parsed
    return None


def parse_ka_date(value: str) -> datetime | None:
    """Parse a Georgian listing date such as ``17 ოქტომბერი 2026, 11:28``.

    Args:
        value: Text containing a date.

    Returns:
        Naive UTC datetime, or None.
    """
    match = re.search(r"(\d{1,2})\s+(\S+)\s+(\d{4})[^\d]*(\d{1,2}):(\d{2})", value)
    if not match:
        return None
    day, month_name, year, hour, minute = match.groups()
    month = KA_MONTHS.get(month_name)
    if month is None:
        return None
    try:
        local = datetime(int(year), month, int(day), int(hour), int(minute))
    except ValueError:
        return None
    return local - TBILISI


def parse_rss(xml: str) -> tuple[RawItem, ...]:
    """Extract items from an RSS 2.0 feed.

    Args:
        xml: Feed body.

    Returns:
        Items in feed order.

    Notes:
        Regex rather than a DOM: feeds are flat, and a strict parser would throw away an entire source on one
        malformed entity.
    """
    items: list[RawItem] = []
    for block in re.findall(r"<item>(.*?)</item>", xml, re.DOTALL):
        link = re.search(r"<link>(.*?)</link>", block, re.DOTALL)
        title = re.search(r"<title>(.*?)</title>", block, re.DOTALL)
        if not link or not title:
            continue
        date = re.search(r"<pubDate>(.*?)</pubDate>", block, re.DOTALL)
        items.append(
            RawItem(
                url=clean_text(link.group(1)),
                title=clean_text(title.group(1)),
                published_at=parse_iso(date.group(1)) if date else None,
            )
        )
    return tuple(items)


def parse_sitemap(xml: str, *, base_url: str, pattern: str) -> tuple[str, ...]:
    """Return sitemap URLs matching a path pattern.

    Args:
        xml: Sitemap body.
        base_url: Origin used to join relative locations.
        pattern: Regular expression the path must match.

    Returns:
        Absolute URLs, in sitemap order.

    Notes:
        The sitemap is the discovery path for TV Pirveli, whose listing is JavaScript-driven: without it the
        pipeline would scrape an empty shell and report zero articles every night.
    """
    urls: list[str] = []
    for loc in re.findall(r"<loc>(.*?)</loc>", xml):
        candidate = urljoin(base_url, clean_text(loc))
        if re.search(pattern, candidate):
            urls.append(candidate)
    return tuple(urls)


def parse_listing(
    html_body: str, *, base_url: str, link_pattern: str, title_tag: str = "h3"
) -> tuple[RawItem, ...]:
    """Extract headline cards from a listing page.

    Args:
        html_body: Page body.
        base_url: Origin for relative links.
        link_pattern: Regular expression the href must match.
        title_tag: Preferred tag for the headline; any ``h1`` to ``h4`` is accepted as a fallback, then the
            anchor's own text.

    Returns:
        Items, de-duplicated by URL and in page order.
    """
    items: list[RawItem] = []
    seen: set[str] = set()
    # The caller's pattern is wrapped in a non-capturing group: it may contain an alternation, and without
    # the group the `|` splits the whole href expression instead of the pattern (measured 2026-11-26, when
    # `/ka/siaxleebi/|/ge/` silently matched nothing).
    for match in re.finditer(
        rf'<a[^>]+href="(?P<href>[^"]*(?:{link_pattern})[^"]*)"[^>]*>(?P<body>.*?)</a>',
        html_body,
        re.DOTALL,
    ):
        href = match.group("href")
        url = urljoin(base_url, href)
        if url in seen:
            continue
        body = match.group("body")
        title_match = (
            re.search(rf"<{title_tag}[^>]*>(.*?)</{title_tag}>", body, re.DOTALL)
            or re.search(r"<h[1-4][^>]*>(.*?)</h[1-4]>", body, re.DOTALL)
            or re.search(r"<p[^>]*>(.*?)</p>", body, re.DOTALL)
        )
        title = clean_text(title_match.group(1)) if title_match else clean_text(body)
        if not title or len(title) < 12:
            # A card whose text is a thumbnail or a nav label is not an article.
            continue
        seen.add(url)
        items.append(
            RawItem(url=url, title=title, published_at=parse_ka_date(clean_text(body)))
        )
    return tuple(items)


# Category words that appear together in a site's navigation and almost never together in a sentence.
NAV_TOKENS = frozenset(
    {
        "სიახლეები",
        "პოლიტიკა",
        "საზოგადოება",
        "კრიმინალი",
        "მსოფლიო",
        "სპორტი",
        "ეკონომიკა",
        "კულტურა",
        "ტექნოლოგიები",
        "ტაბლოიდი",
        "გადაცემები",
    }
)


def _is_navigation(text: str) -> bool:
    """Return True when a paragraph is the site menu rather than prose.

    Args:
        text: Paragraph text.

    Returns:
        True when at least three category words appear in it.

    Notes:
        Measured 2026-11-26: requiring sentence punctuation was not enough, because the menu paragraph carried
        a separator mark; the excerpt of every publication began with "სიახლეები პოლიტიკა …".
    """
    hits = sum(1 for token in NAV_TOKENS if token in text)
    return hits >= 3


# A paragraph that is mostly markup rather than prose: measured 2026-11-26, a TV Pirveli article's first
# "paragraph" was 12,858 characters of `<path d="M18.759,7.066...">` SVG data. It passed every length and
# punctuation check, so the stored excerpt for that publication was icon geometry, and stance was labelled on it.
_MARKUP_MARKERS = ('data-name=', 'd="M', "<path", "svg", "&nbsp;")
_GEORGIAN = re.compile(r"[\u10A0-\u10FF]")
# Related-article blocks carry a heading like this; everything after it belongs to another story.
TEASER_MARKERS = ("ასევე", "მსგავსი", "სხვა სიახლე", "read also", "related")
# A teaser is a short standalone label ("ვაპირებთ ბრძოლას მანამ..."), not a paragraph of prose.
TEASER_MAX_CHARS = 140
LEAD_PARAGRAPHS_KEPT = 2


def _is_markup(text: str) -> bool:
    """Return True when a "paragraph" is markup or a placeholder rather than prose.

    Args:
        text: Paragraph text.

    Returns:
        True when it contains SVG or HTML fragments, or is mostly non-Georgian.
    """
    lowered = text.lower()
    if any(marker in lowered for marker in _MARKUP_MARKERS):
        return True
    georgian = len(_GEORGIAN.findall(text))
    return georgian < max(20, int(len(text) * 0.5))


def _is_teaser(text: str) -> bool:
    """Return True when a paragraph looks like a related-article label.

    Args:
        text: Paragraph text.

    Returns:
        True for a short line that is not a sentence.
    """
    return len(text) < TEASER_MAX_CHARS and not text.rstrip().endswith((".", "!", "?"))


def extract_excerpt(page: str, *, max_chars: int = 1500) -> str:
    """Return the first meaningful prose from an article page.

    Args:
        page: Article HTML.
        max_chars: Maximum excerpt length.

    Returns:
        The longest gap-free run of opening paragraphs that looks like prose, or an empty string.

    Notes:
        Navigation renders as paragraphs too. The first paragraph of a Georgian news page is typically the
        category menu, so the extractor skips short and menu-like lines instead of trusting position.
    """
    paragraphs = [
        clean_text(match) for match in re.findall(r"<p[^>]*>(.*?)</p>", page, re.DOTALL)
    ]
    prose = [
        text
        for text in paragraphs
        if len(text) > 60
        and not _is_markup(text)
        and not _is_navigation(text)
        # A category menu renders as one long paragraph of capitalised words with no sentence
        # punctuation. Requiring punctuation is crude, but it is exactly the difference between
        # "სიახლეები პოლიტიკა საზოგადოება" and a sentence, and it needs no vocabulary list.
        and any(mark in text for mark in (".", ",", "!", "?", "—"))
    ]

    kept: list[str] = []
    for index, text in enumerate(prose):
        if any(marker.lower() in text.lower() for marker in TEASER_MARKERS):
            break  # everything from here on belongs to another story
        if index < LEAD_PARAGRAPHS_KEPT or not _is_teaser(text):
            kept.append(text)
    if not kept:
        return ""
    joined = " ".join(kept)
    return joined[:max_chars]


def body_fingerprint(text: str) -> str:
    """Return a stable hash of article text.

    Args:
        text: Extracted text.

    Returns:
        Hex sha256, used to detect republication and to compare without storing the text.
    """
    return hashlib.sha256(" ".join(text.split()).encode("utf-8")).hexdigest()


def publication_id(source_id: str, url: str) -> str:
    """Return a stable id for a publication.

    Args:
        source_id: Source key.
        url: Article URL.

    Returns:
        Deterministic id, so re-ingesting updates rather than duplicates.
    """
    return hashlib.sha256(f"{source_id}\x1f{url}".encode()).hexdigest()[:32]


def looks_like_article(url: str) -> bool:
    """Return True when a URL points at an article rather than a section.

    Args:
        url: Absolute URL.

    Returns:
        True when a path segment begins with digits, which is how these CMSs name articles
        (``/ka/siaxleebi/politika/139842-slug``).

    Notes:
        Measured 2026-11-26: the section page also links to sibling sections (``/ka/siaxleebi/teqnologiebi``),
        and those were being stored as publications with a category name as their title.
    """
    from urllib.parse import urlparse

    path = urlparse(url).path
    # Two shapes measure the same thing: TV Pirveli writes `/139842-slug`, Imedi writes `/484181/slug`.
    return re.search(r"/\d{3,}(?:-|/)", path) is not None


def parse_sitemap_dates(xml: str) -> dict[str, datetime | None]:
    """Return URL to last-modified timestamp from a sitemap.

    Args:
        xml: Sitemap body.

    Returns:
        Mapping of absolute URL to a naive UTC datetime (or None when a timestamp is unparseable).

    Notes:
        Imedi's sitemap carries ``<lastmod>`` for every URL. Reading it avoids re-fetching 400 article pages
        just to learn when they were published — which is the difference between a one-request backfill and a
        seven-minute one.
    """
    dates: dict[str, datetime | None] = {}
    for block in re.findall(r"<url>(.*?)</url>", xml, re.DOTALL):
        loc = re.search(r"<loc>(.*?)</loc>", block, re.DOTALL)
        if not loc:
            continue
        lastmod = re.search(r"<lastmod>(.*?)</lastmod>", block, re.DOTALL)
        parsed: datetime | None = None
        if lastmod:
            raw = clean_text(lastmod.group(1))
            for pattern in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
                try:
                    parsed = datetime.strptime(raw, pattern)
                except ValueError:
                    continue
                break
        dates[clean_text(loc.group(1))] = parsed
    return dates


def newest_first(urls: Iterable[str], *, limit: int) -> tuple[str, ...]:
    """Order article URLs newest-first by their embedded id.

    Args:
        urls: Article URLs.
        limit: Maximum to keep.

    Returns:
        The URLs with the highest numeric id, newest first.

    Notes:
        Both CMSs encode a monotonic id in the path (``/ka/siaxleebi/politika/139842-…``,
        ``/ge/politika/484181/…``). Sorting by it is a cheap approximation of recency that needs no per-site
        pagination logic — and a backfill of "the last N articles" is exactly what a comparison needs.
    """
    numbered: list[tuple[int, str]] = []
    for url in urls:
        match = re.search(r"/(\d{3,})(?:-|/)", url)
        if match:
            numbered.append((int(match.group(1)), url))
    numbered.sort(key=lambda pair: pair[0], reverse=True)
    return tuple(url for _id, url in numbered[:limit])


def dedupe_by_title(items: Iterable[RawItem]) -> tuple[RawItem, ...]:
    """Drop items whose headline repeats an earlier one.

    Args:
        items: Discovered items.

    Returns:
        Items whose normalised title appears once.

    Notes:
        Sites republish the same story under two URLs; storing both inflates counts and makes a topic look
        twice as busy as it is.
    """
    seen: set[str] = set()
    kept: list[RawItem] = []
    for item in items:
        key = " ".join(item.title.lower().split())
        if key in seen:
            continue
        seen.add(key)
        kept.append(item)
    return tuple(kept)
