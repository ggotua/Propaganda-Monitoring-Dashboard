"""Public report tests (SPEC-018).

The public page is the artefact a stranger reads first, so the tests check the two things that would mislead
them: a figure that describes the wrong corpus, and a page that needs the network to render.
"""

from __future__ import annotations

from datetime import date

from gtaf.application.report_public import build_public_report
from gtaf.presentation.report_public import render_public_report


class _Reader:
    """Fake storage with two outlets and two figures."""

    def publication_stats(self):
        """Return per-source totals, with one outlet's leaning unassigned."""
        return (
            ("imedi", "pro-government", 10, 10, "2026-11-03", "2026-11-13"),
            ("tvpirveli", "opposition", 8, 8, "2026-11-03", "2026-11-13"),
            ("rustavi2", "independent", 4, 4, "2026-11-20", "2026-11-21"),
        )

    def publication_stance_counts(self, target: str):
        """Return a fixed distribution for the prime minister only."""
        if target != "kobakhidze":
            return ()
        return (
            ("pro-government", "imedi", "neutral", 5),
            ("opposition", "tvpirveli", "critical", 4),
        )


def test_groups_sum_per_leaning_and_group() -> None:
    """The headline table is what a reader quotes, so its arithmetic must be checkable."""
    report = build_public_report(
        _Reader(),
        generated_on=date(2026, 11, 28),
        leaning_assigned={"imedi": True, "tvpirveli": True, "rustavi2": False},
        versions=(("matcher", "matcher-2026-11-28"),),
    )

    government = next(
        row for row in report.groups if row.group == "government" and row.leaning == "pro-government"
    )
    opposition = next(
        row for row in report.groups if row.group == "government" and row.leaning == "opposition"
    )

    assert government.publications == 5
    assert government.critical == 0
    assert opposition.publications == 4
    assert opposition.critical == 4
    assert opposition.critical_rate == 1.0


def test_unassigned_leaning_is_marked_in_the_page() -> None:
    """An outlet without an editorial leaning must never be presented as if it had one."""
    report = build_public_report(
        _Reader(),
        generated_on=date(2026, 11, 28),
        leaning_assigned={"imedi": True, "tvpirveli": True, "rustavi2": False},
        versions=(("matcher", "matcher-2026-11-28"),),
    )

    markup = render_public_report(report)

    assert "unassigned" in markup
    assert "rustavi2" in markup


def test_page_is_bilingual_and_self_contained() -> None:
    """Two languages, no network: the page is published as a single file."""
    report = build_public_report(
        _Reader(),
        generated_on=date(2026, 11, 28),
        leaning_assigned={"imedi": True, "tvpirveli": True, "rustavi2": False},
        versions=(("matcher", "matcher-2026-11-28"),),
    )

    markup = render_public_report(report)

    assert 'data-lang="ka"' in markup or "data-lang='ka'" in markup
    assert "data-ka=" in markup
    assert 'src="http' not in markup
    assert 'href="http' not in markup
    assert "@import" not in markup


def test_page_states_that_it_is_not_airtime() -> None:
    """The corpus notice is the one sentence that must survive any edit."""
    report = build_public_report(
        _Reader(),
        generated_on=date(2026, 11, 28),
        leaning_assigned={"imedi": True, "tvpirveli": True, "rustavi2": False},
        versions=(("matcher", "matcher-2026-11-28"),),
    )
    markup = render_public_report(report)

    assert "not airtime" in markup
    assert "0.673" in markup
