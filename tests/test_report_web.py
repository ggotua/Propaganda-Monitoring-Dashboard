"""Web report tests (SPEC-018).

The report is where a reader meets the numbers, so the tests check the two things that would mislead them: a
figure computed in the wrong place, and a page that silently needs the network.
"""

from __future__ import annotations

from datetime import date

from gtaf.application.report_web import ConcordanceBlock, build_web_report
from gtaf.domain.actors import Actor
from gtaf.presentation.report_web import render_web_report


class _Reader:
    """Fake storage with two sources and one stance table."""

    def publication_stats(self):
        """Return per-source totals."""
        return (
            ("imedi", "pro-government", 3, 3, "2026-11-05", "2026-11-07"),
            ("tvpirveli", "opposition", 2, 2, "2026-11-05", "2026-11-06"),
        )

    def list_publications(self, *, source_id=None, limit=500):
        """Return publications mentioning the actor in one source."""
        return (
            ("p1", "imedi", "პრემიერი კობახიძე", "ტექსტი", "pro-government"),
            ("p2", "imedi", "პარლამენტი", "ტექსტი", "pro-government"),
            ("p3", "imedi", "სხვა", "ტექსტი", "pro-government"),
            ("p4", "tvpirveli", "კობახიძე და ოპოზიცია", "ტექსტი", "opposition"),
            ("p5", "tvpirveli", "ეკონომიკა", "ტექსტი", "opposition"),
        )

    def publication_stance_counts(self, target: str):
        """Return a stance distribution split by leaning."""
        if target != "kobakhidze":
            return ()
        return (
            ("opposition", "tvpirveli", "critical", 2),
            ("opposition", "tvpirveli", "neutral", 1),
            ("pro-government", "imedi", "supportive", 1),
        )


def _actor() -> Actor:
    """Return a single actor for mention counting."""
    return Actor(actor_id="kobakhidze", ka="კობახიძე", en="Kobakhidze", aliases=())


def test_report_computes_mention_shares_per_source() -> None:
    """A share, not a count: the sources differ in size and a count would measure corpus size."""
    report = build_web_report(
        _Reader(),
        actors=[_actor()],
        stance_targets=["kobakhidze"],
        concordance=None,
        generated_on=date(2026, 11, 26),
    )

    imedi = next(item for item in report.sources if item.source_id == "imedi")
    tvpirveli = next(item for item in report.sources if item.source_id == "tvpirveli")

    assert imedi.mentions[0][1] == 1
    assert round(imedi.mentions[0][2], 4) == round(1 / 3, 4)
    assert round(tvpirveli.mentions[0][2], 4) == 0.5


def test_report_keeps_stance_split_by_leaning() -> None:
    """Merging the leanings would hide the thing the report exists to show."""
    report = build_web_report(
        _Reader(),
        actors=[_actor()],
        stance_targets=["kobakhidze"],
        concordance=None,
        generated_on=date(2026, 11, 26),
    )

    block = report.stance[0]
    assert {row[1] for row in block.rows} == {"opposition", "pro-government"}
    critical_row = next(row for row in block.rows if row[1] == "opposition")
    assert critical_row[3] == 2


def test_missing_concordance_refuses_the_airtime_claim() -> None:
    """With no comparison there is no licence to call web numbers airtime."""
    report = build_web_report(
        _Reader(),
        actors=[_actor()],
        stance_targets=[],
        concordance=None,
        generated_on=date(2026, 11, 26),
    )

    assert report.concordance.available is False
    assert "airtime" in report.concordance.verdict


def test_rendered_report_is_self_contained() -> None:
    """The file must open from an email attachment with no network: no remote stylesheet, font or script."""
    report = build_web_report(
        _Reader(),
        actors=[_actor()],
        stance_targets=["kobakhidze"],
        concordance=ConcordanceBlock(
            available=True,
            source_id="imedi",
            start=date(2026, 11, 3),
            end=date(2026, 11, 13),
            segments=4837,
            publications=125,
            rho=0.736,
            verdict="Concordant.",
        ),
        generated_on=date(2026, 11, 26),
    )

    markup = render_web_report(report)

    assert "<script" not in markup
    assert 'href="http' not in markup
    assert "@import" not in markup
    assert "rho = 0.74" in markup
    assert "Corpus notice" in markup


def test_rendered_report_labels_the_corpus() -> None:
    """Every rendered figure sits under a notice that it describes websites, not airtime."""
    report = build_web_report(
        _Reader(),
        actors=[_actor()],
        stance_targets=[],
        concordance=None,
        generated_on=date(2026, 11, 26),
    )
    markup = render_web_report(report)

    assert "not airtime" in markup
