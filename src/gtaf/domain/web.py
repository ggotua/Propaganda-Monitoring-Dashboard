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
        title_tag: Tag that holds the headline inside the card.

    Returns:
        Items, de-duplicated by URL and in page order.
    """
    items: list[RawItem] = []
    seen: set[str] = set()
    for match in re.finditer(
        rf'<a[^>]+href="(?P<href>[^"]*{link_pattern}[^"]*)"[^>]*>(?P<body>.*?)</a>',
        html_body,
        re.DOTALL,
    ):
        href = match.group("href")
        url = urljoin(base_url, href)
        if url in seen:
            continue
        body = match.group("body")
        title_match = re.search(rf"<{title_tag}[^>]*>(.*?)</{title_tag}>", body, re.DOTALL) or re.search(
            r"<h[23][^>]*>(.*?)</h[23]>", body, re.DOTALL
        )
        title = clean_text(title_match.group(1)) if title_match else clean_text(body)
        if not title or len(title) < 12:
            # A card whose text is a thumbnail or a nav label is not an article.
            continue
        seen.add(url)
        items.append(RawItem(url=url, title=title))
    return tuple(items)


def extract_excerpt(page: str, *, max_chars: int = 400) -> str:
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
        # A category menu renders as one long paragraph of capitalised words with no sentence
        # punctuation. Requiring punctuation is crude, but it is exactly the difference between
        # "სიახლეები პოლიტიკა საზოგადოება" and a sentence, and it needs no vocabulary list.
        and any(mark in text for mark in (".", ",", "!", "?", "—"))
    ]
    if not prose:
        return ""
    joined = " ".join(prose)
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
