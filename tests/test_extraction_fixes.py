"""Regression tests for the four pipeline defects a human review found on 2026-11-27.

Each defect produced a wrong label that looked like a model error and was not: a vocative surname missed by the
matcher, a street name read as a person, SVG geometry read as prose, and a related-article teaser read as the
article's own position.
"""

from __future__ import annotations

from gtaf.domain.actors import Actor, find_mentions, match_token
from gtaf.domain.web import extract_excerpt


def _kobakhidze() -> Actor:
    """Return the dictionary entry under test."""
    return Actor(actor_id="kobakhidze", ka="კობახიძე", en="Kobakhidze", aliases=())


def test_vocative_surname_matches() -> None:
    """Measured 2026-11-27: row 32, "კობახიძევ, ქვეყანა არ არის შენი და შენი პარტიის მაღაზია" — the most direct
    criticism in the batch — was never matched, because the vocative ending -ევ was absent."""
    mention = match_token("კობახიძევ", _kobakhidze())

    assert mention is not None
    assert mention.actor_id == "kobakhidze"


def test_dative_and_instrumental_surnames_match() -> None:
    """-ეს and -ით were also missing, and they are ordinary case forms of the same name."""
    assert match_token("კობახიძეს", _kobakhidze()) is not None
    assert match_token("კობახიძით", _kobakhidze()) is not None


def test_street_name_is_not_a_person() -> None:
    """Measured 2026-11-27: a water-outage notice listing "კობახიძის" as a street produced a mention with no
    person in it."""
    text = "27 ნოემბერს წყალი არ მიეწოდება კობახიძის ქუჩას და მიმდებარე ქუჩებს."

    assert find_mentions(text, (_kobakhidze(),)) == ()


def test_a_person_followed_by_another_word_still_matches() -> None:
    """The street guard must not swallow ordinary text."""
    text = "კობახიძემ დღეს განაცხადა, რომ მოლაპარაკებები გაგრძელდება."

    assert find_mentions(text, (_kobakhidze(),)) != ()


def test_svg_geometry_is_not_an_excerpt() -> None:
    """Measured 2026-11-27: a TV Pirveli page's first "paragraph" was 12,858 characters of `<path d="M18.759...">`,
    and the stored excerpt for that publication was icon geometry."""
    page = (
        '<p><path id="Fill_3" data-name="Fill 3" d="M17.218,7.066V21.994H12.476a1.434,1.434,0,0,1-1.436-1.435V5.738c0-1.113-.763-2.1-2.431-2.1s-2.431.991-2.431,2.1V21.994H12"</p>'
        "<p>როგორც უწყებაში ამტკიცებენ, თადუმაძემ თანამდებობიდან პირადი განცხადების საფუძველზე გათავისუფლდა.</p>"
    )

    excerpt = extract_excerpt(page)

    assert "data-name" not in excerpt
    assert excerpt.startswith("როგორც უწყებაში")


def test_short_teaser_line_is_dropped_after_the_lead() -> None:
    """Measured 2026-11-27: row 17's only Ivanishvili line was a teaser for another story, and the model's
    `critical` label came from it. Short unattributed lines after the lead are teasers, not the article."""
    page = (
        "<p>როგორც უწყებაში ამტკიცებენ, თადუმაძემ თანამდებობიდან პირადი განცხადების საფუძველზე გათავისუფლდა.</p>"
        "<p>რაც შეეხება თეიმურაზ კუპატაძეს, ის ამ დრომდე დეპარტამენტის დირექტორის მოადგილედ მუშაობს, "
        "თუმცა უწყებაში აცხადებენ, რომ მისი გათავისუფლება უახლოეს დღეებში მოხდება.</p>"
        '<p>&quot;ვაპირებთ ბრძოლას მანამ, სანამ საქართველო არ გამთლიანდება&quot;</p>'
    )

    excerpt = extract_excerpt(page)

    assert "გამთლიანდება" not in excerpt


def test_teaser_marker_cuts_the_excerpt() -> None:
    """A related-article heading ends the article text, whatever follows it."""
    page = (
        "<p>როგორც უწყებაში ამტკიცებენ, თადუმაძემ თანამდებობიდან პირადი განცხადების საფუძველზე გათავისუფლდა.</p>"
        "<p>ასევე: ივანიშვილზე ზეწოლა უფრო ქმედითი უნდა იყოს, აცხადებენ არასამთავრობო ორგანიზაციებში.</p>"
    )

    excerpt = extract_excerpt(page)

    assert "ზეწოლა" not in excerpt
