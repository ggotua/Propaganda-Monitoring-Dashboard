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


def test_confusable_surname_is_not_the_actor() -> None:
    """Measured 2026-11-27: "ზურაბაშვილი" (the PM's representative to Russia) was fuzzy-matched to
    "ზურაბიშვილი" (the former president), and two unrelated stories were labelled as if they were about her."""
    zourabichvili = Actor(actor_id="zourabichvili", ka="ზურაბიშვილი", en="Zourabichvili", aliases=())

    assert match_token("ზურაბაშვილმა", zourabichvili) is None
    assert match_token("ზურაბაშვილი", zourabichvili) is None
    assert match_token("ზურაბიშვილი", zourabichvili) is not None


def test_container_end_inside_the_body_does_not_empty_the_excerpt() -> None:
    """Measured 2026-11-27: cutting at the next `class="page__` marker hit `page__comments` inside the article
    container, leaving 14 of 30 reviewed rows with an empty excerpt."""
    page = (
        '<div class="page__usercontent">'
        "<p>ბიძინა ივანიშვილის ყოფილმა ადვოკატმა, შალვა თადუმაძემ შს მინისტრის მოადგილის პოსტი დატოვა.</p>"
        '<div class="page__comments">'
        "<p>კომენტარები გამორთულია ამ სტატიისთვის, თუმცა დისკუსია გრძელდება სოციალურ ქსელებში.</p>"
        "</div></div>"
        '<div class="page__similar"><p>სხვა სიახლე, რომელიც თქვენთვის საინტერესო იქნება დღეს.</p></div>'
    )

    excerpt = extract_excerpt(page)

    assert "თადუმაძემ" in excerpt
    assert "კომენტარები" not in excerpt


def test_different_first_name_same_surname_is_not_the_actor() -> None:
    """Measured 2026-11-27: "ადიკო ივანიშვილი" and "ბერა ივანიშვილი" were both counted as Bidzina
    Ivanishvili, so a protest story about a namesake was labelled as if it were about the party founder."""
    ivanishvili = Actor(actor_id="ivanishvili", ka="ივანიშვილი", en="Ivanishvili", aliases=())

    assert find_mentions("ადიკო ივანიშვილმა დღეს განაცხადა, რომ დაბრუნდება.", (ivanishvili,)) == ()
    assert find_mentions("ბერა ივანიშვილი კონცერტს გამართავს.", (ivanishvili,)) == ()


def test_first_name_alone_is_not_the_actor() -> None:
    """Measured 2026-11-28: an alias of "ბიძინა" alone matched Bidzina Giorgobiani, a different politician, so
    the alias was removed and the first name now has to stand next to the surname."""
    ivanishvili = Actor(
        actor_id="ivanishvili", ka="ივანიშვილი", en="Ivanishvili", aliases=("ბიძინა ივანიშვილი",)
    )

    assert find_mentions("ბიძინა გიორგობიანი: ხელისუფლებამ თავი უნდა დაანებოს.", (ivanishvili,)) == ()
    assert find_mentions("ბიძინა ივანიშვილმა დღეს განაცხადა, რომ მოლაპარაკებები გაგრძელდება.", (ivanishvili,)) != ()


def test_phrase_alias_names_the_actor_without_the_surname() -> None:
    """"ოცნების დამფუძნებელი" is how the outlets name him without the surname."""
    ivanishvili = Actor(
        actor_id="ivanishvili",
        ka="ივანიშვილი",
        en="Ivanishvili",
        aliases=("ბიძინა ივანიშვილი", "ოცნების დამფუძნებელი"),
    )

    mentions = find_mentions("ოცნების დამფუძნებელი დღეს შეხვედრას გამართავს.", (ivanishvili,))

    assert [mention.actor_id for mention in mentions] == ["ivanishvili"]


def test_namesake_taints_the_whole_text() -> None:
    """Measured 2026-11-27: a story about Adiko Ivanishvili also said "ივანიშვილი" later, so dropping only the
    namesake token left Bidzina in place for that article."""
    ivanishvili = Actor(actor_id="ivanishvili", ka="ივანიშვილი", en="Ivanishvili", aliases=())
    text = "ადიკო ივანიშვილმა კონცერტი გამართა. ივანიშვილმა ასევე აღნიშნა, რომ დაბრუნდება."

    assert find_mentions(text, (ivanishvili,)) == ()


def test_bare_surname_requires_the_first_name() -> None:
    """Measured 2026-11-28: the reviewer required Bidzina's first name or a known alias before matching him,
    because "ივანიშვილი" alone is shared with relatives the corpus does not track."""
    ivanishvili = Actor(actor_id="ivanishvili", ka="ივანიშვილი", en="Ivanishvili", aliases=())

    assert find_mentions("ივანიშვილმა დღეს განაცხადა, რომ მოლაპარაკებები გაგრძელდება.", (ivanishvili,)) == ()
    assert find_mentions("ბიძინა ივანიშვილმა დღეს განაცხადა, რომ მოლაპარაკებები გაგრძელდება.", (ivanishvili,)) != ()


def test_teaser_outside_the_body_container_is_excluded() -> None:
    """Measured 2026-11-27: a related-article sentence ("Kurtulmuş said…") sat at the end of a stored excerpt and
    could carry a stance. TV Pirveli keeps the body in `page__usercontent` and teasers outside it."""
    page = (
        '<div class="page__header">menu</div>'
        '<div class="page__usercontent">'
        "<p>როგორც უწყებაში ამტკიცებენ, თადუმაძემ თანამდებობიდან პირადი განცხადების საფუძველზე გათავისუფლდა.</p>"
        "</div>"
        '<div class="page__similar">'
        "<p>კურტულმუშმა განაცხადა, რომ თურქეთი მზადაა შუამავლობისთვის და ეს პროცესი გაგრძელდება.</p>"
        "</div>"
    )

    excerpt = extract_excerpt(page)

    assert "თადუმაძემ" in excerpt
    assert "კურტულმუშმა" not in excerpt


def test_teaser_marker_cuts_the_excerpt() -> None:
    """A related-article heading ends the article text, whatever follows it."""
    page = (
        "<p>როგორც უწყებაში ამტკიცებენ, თადუმაძემ თანამდებობიდან პირადი განცხადების საფუძველზე გათავისუფლდა.</p>"
        "<p>ასევე: ივანიშვილზე ზეწოლა უფრო ქმედითი უნდა იყოს, აცხადებენ არასამთავრობო ორგანიზაციებში.</p>"
    )

    excerpt = extract_excerpt(page)

    assert "ზეწოლა" not in excerpt
