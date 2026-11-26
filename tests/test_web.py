"""Web parsing tests (SPEC-018).

All fixtures are inline strings, so no test touches the network. The parsers exist to be broken by a site
redesign in a test, not in a nightly run.
"""

from __future__ import annotations

from datetime import datetime

from gtaf.domain.web import (
    RawItem,
    body_fingerprint,
    clean_text,
    dedupe_by_title,
    extract_excerpt,
    parse_ka_date,
    parse_listing,
    parse_rss,
    parse_sitemap,
    publication_id,
)


def test_clean_text_decodes_entities_and_collapses_space() -> None:
    """Listings carry entities and double spaces; both must go."""
    assert clean_text("  First &amp;  best\n") == "First & best"


def test_parse_rss_reads_link_title_and_date() -> None:
    """The RSS path is what four sources depend on."""
    xml = """
    <rss><channel><item>
      <title>პარლამენტმა კანონპროექტი მიიღო</title>
      <link>https://publika.ge/article/1</link>
      <pubDate>Wed, 26 Nov 2026 10:30:00 +0000</pubDate>
    </item></channel></rss>
    """
    items = parse_rss(xml)

    assert len(items) == 1
    assert items[0].title == "პარლამენტმა კანონპროექტი მიიღო"
    assert items[0].url == "https://publika.ge/article/1"
    assert items[0].published_at == datetime(2026, 11, 26, 10, 30)


def test_parse_rss_skips_items_without_a_link() -> None:
    """A malformed item must drop itself, not the feed."""
    xml = "<rss><channel><item><title>No link</title></item></channel></rss>"
    assert parse_rss(xml) == ()


def test_parse_ka_date_shifts_tbilisi_to_utc() -> None:
    """Georgia is UTC+4 year-round (D-012); the listing time is local."""
    assert parse_ka_date("პოლიტიკა · 17 ოქტომბერი 2026, 11:28") == datetime(2026, 10, 17, 7, 28)


def test_parse_ka_date_rejects_garbage() -> None:
    """An unreadable date yields None rather than a wrong one."""
    assert parse_ka_date("no date here") is None


def test_parse_sitemap_filters_by_pattern() -> None:
    """TV Pirveli's listing is JavaScript-driven, so the sitemap is the discovery path."""
    xml = """
    <urlset>
      <url><loc>https://tvpirveli.ge/ka/siaxleebi/politika/139795-slug</loc></url>
      <url><loc>https://tvpirveli.ge/ka/sport/12-other</loc></url>
    </urlset>
    """
    urls = parse_sitemap(xml, base_url="https://tvpirveli.ge", pattern=r"/ka/siaxleebi/")

    assert urls == ("https://tvpirveli.ge/ka/siaxleebi/politika/139795-slug",)


def test_parse_listing_extracts_cards() -> None:
    """A listing card is a link that wraps a headline."""
    body = """
    <a href="/ka/siaxleebi/politika/139795-garibashvili"><h3>გარიბაშვილი პროკურატურას აკრიტიკებს</h3></a>
    <a href="/ka/siaxleebi/politika/139796-some"><h3>მეორე სიახლე პარლამენტიდან დღეს</h3></a>
    """
    items = parse_listing(
        body, base_url="https://tvpirveli.ge", link_pattern=r"/ka/siaxleebi/"
    )

    assert len(items) == 2
    assert items[0].url.startswith("https://tvpirveli.ge/ka/siaxleebi/")
    assert "გარიბაშვილი" in items[0].title


def test_parse_listing_drops_nav_labels() -> None:
    """A card whose text is a menu word is not an article."""
    body = '<a href="/ka/siaxleebi/x"><h3>სიახლეები</h3></a>'
    assert parse_listing(body, base_url="https://tvpirveli.ge", link_pattern=r"/ka/siaxleebi/") == ()


def test_extract_excerpt_skips_the_menu_paragraph() -> None:
    """The first paragraph of a Georgian news page is the category menu, not prose."""
    page = (
        "<p>სიახლეები პოლიტიკა საზოგადოება კრიმინალი მსოფლიო სპორტი ეკონომიკა</p>"
        "<p>პარლამენტმა დღეს მიიღო კანონპროექტი, რომელიც ცვლის საარჩევნო სისტემას და "
        "ძალაში შედის 2027 წლის იანვრიდან.</p>"
    )
    excerpt = extract_excerpt(page)

    assert "საარჩევნო სისტემას" in excerpt
    assert "სპორტი" not in excerpt


def test_body_fingerprint_is_stable_across_whitespace() -> None:
    """Whitespace must not change the fingerprint, or every refetch looks like new content."""
    assert body_fingerprint("a  b\nc") == body_fingerprint("a b c")


def test_publication_id_is_deterministic_and_url_specific() -> None:
    """Re-ingesting updates the row instead of duplicating it."""
    first = publication_id("tvpirveli", "https://tvpirveli.ge/a")
    assert first == publication_id("tvpirveli", "https://tvpirveli.ge/a")
    assert first != publication_id("tvpirveli", "https://tvpirveli.ge/b")
    assert first != publication_id("imedi", "https://tvpirveli.ge/a")


def test_dedupe_by_title_keeps_the_first() -> None:
    """Sites republish one story under two URLs; storing both doubles a topic's apparent activity."""
    items = (
        RawItem("https://x/1", "Same  Headline"),
        RawItem("https://x/2", "same headline"),
        RawItem("https://x/3", "Other"),
    )
    kept = dedupe_by_title(items)

    assert [item.url for item in kept] == ["https://x/1", "https://x/3"]
