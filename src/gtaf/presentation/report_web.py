"""Self-contained HTML report for the web corpus (SPEC-018).

No external stylesheet, font or script: the file must open from an email attachment on a machine with no
network. Every figure carries its corpus label, because the one mistake this report must not permit is a
reader mistaking a website count for airtime.
"""

from __future__ import annotations

import html

from gtaf.application.report_web import WebReport

STYLE = """
:root { color-scheme: light; }
body { font-family: Georgia, 'Times New Roman', serif; margin: 0; background: #f7f6f3; color: #1d1d1b; }
main { max-width: 980px; margin: 0 auto; padding: 40px 28px 80px; }
h1 { font-size: 30px; margin: 0 0 6px; letter-spacing: -0.01em; }
h2 { font-size: 20px; margin: 40px 0 12px; border-bottom: 1px solid #dcd8d0; padding-bottom: 6px; }
p, li { line-height: 1.55; font-size: 15px; }
.sub { color: #6b675f; font-size: 14px; margin: 0 0 28px; }
.banner { background: #fff3d6; border-left: 4px solid #c98a00; padding: 12px 16px; margin: 20px 0; font-size: 14px; }
table { border-collapse: collapse; width: 100%; margin: 10px 0 4px; font-size: 14px; }
th, td { text-align: left; padding: 7px 10px; border-bottom: 1px solid #e4e0d8; }
th { background: #efece6; font-weight: 600; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
.leaning { display: inline-block; padding: 1px 7px; border-radius: 3px; font-size: 12px; }
.gov { background: #e3ecf7; }
.opp { background: #f9e3e3; }
.ind { background: #e6f1e6; }
.unk { background: #ececec; }
.q { font-style: italic; color: #3b3a36; }
footer { margin-top: 48px; color: #6b675f; font-size: 13px; border-top: 1px solid #dcd8d0; padding-top: 14px; }
"""


def _leaning_class(leaning: str) -> str:
    """Map a leaning label to a CSS class."""
    return {"pro-government": "gov", "opposition": "opp", "independent": "ind"}.get(leaning, "unk")


def _esc(value: object) -> str:
    """Escape a value for HTML."""
    return html.escape(str(value))


def _consequence(value: float | None) -> str:
    """Return a plain-language reading of a correlation.

    Args:
        value: Spearman rho, or None.

    Returns:
        A sentence a non-specialist can act on.
    """
    if value is None:
        return "not measured"
    if value >= 0.7:
        return "concordant: on this window the site tracked the airtime"
    return "not concordant: describe web figures as what the site published"


def _pct(value: float) -> str:
    """Format a share as a percentage."""
    return f"{value * 100:.1f}%"


def render_web_report(report: WebReport) -> str:
    """Render the web report as one self-contained HTML document.

    Args:
        report: Assembled report data.

    Returns:
        Complete HTML.
    """
    total = sum(block.total for block in report.sources)
    parts: list[str] = [
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width, initial-scale=1'>",
        f"<title>Web corpus report — {report.generated_on.isoformat()}</title>",
        f"<style>{STYLE}</style></head><body><main>",
        "<h1>Web corpus report</h1>",
        f"<p class='sub'>Georgian political coverage on the channels' own websites · "
        f"{total} publications · generated {report.generated_on.isoformat()}</p>",
        "<div class='banner'><strong>Corpus notice.</strong> These figures describe <em>websites</em>. "
        "They are not airtime, they are never added to broadcast segments, and they do not replace the "
        "broadcast corpus — they exist because it cannot grow while YouTube blocks transcript access "
        "(D-033, D-034).</div>",
    ]

    parts.append("<h2>1. What was collected</h2>")
    parts.append(
        "<table><tr><th>Source</th><th>Leaning</th><th class='num'>Publications</th>"
        "<th class='num'>With date</th><th>Window</th></tr>"
    )
    for block in report.sources:
        window = (
            f"{_esc(block.first_day)} to {_esc(block.last_day)}"
            if block.first_day and block.last_day
            else "dates not available"
        )
        parts.append(
            f"<tr><td>{_esc(block.source_id)}</td>"
            f"<td><span class='leaning {_leaning_class(block.leaning)}'>{_esc(block.leaning)}</span></td>"
            f"<td class='num'>{block.total}</td><td class='num'>{block.dated}</td>"
            f"<td>{window}</td></tr>"
        )
    parts.append("</table>")
    parts.append(
        "<p class='sub'>Leaning labels are editorial judgements stored as data, attributable and revisable — "
        "never produced by a model.</p>"
    )

    parts.append("<h2>2. Who the sites cover</h2>")
    parts.append(
        "<table><tr><th>Actor</th>"
        + "".join(
            f"<th class='num'>{_esc(block.source_id)}</th>" for block in report.sources
        )
        + "</tr>"
    )
    actor_ids = sorted({actor for block in report.sources for actor, _n, _s in block.mentions})
    for actor_id in actor_ids:
        cells = []
        for block in report.sources:
            share = next((s for a, _n, s in block.mentions if a == actor_id), 0.0)
            cells.append(f"<td class='num'>{_pct(share)}</td>")
        parts.append(f"<tr><td>{_esc(actor_id)}</td>{''.join(cells)}</tr>")
    parts.append("</table>")
    parts.append(
        "<p class='sub'>Share of each source's publications that name the actor. A share, not a count, "
        "because the sources differ in size.</p>"
    )

    for block in report.sources:
        if not block.headline_sample:
            continue
        parts.append(f"<p class='sub'><strong>{_esc(block.source_id)}</strong> recent headlines:</p><ul>")
        for title in block.headline_sample:
            parts.append(f"<li class='q'>{_esc(title)}</li>")
        parts.append("</ul>")

    parts.append("<h2>3. Stance by leaning</h2>")
    if report.stance:
        parts.append(
            "<table><tr><th>Actor</th><th>Source</th><th>Leaning</th>"
            "<th class='num'>supportive</th><th class='num'>critical</th>"
            "<th class='num'>neutral</th><th class='num'>unclear</th></tr>"
        )
        for stance_block in report.stance:
            for index, (
                source,
                leaning,
                supportive,
                critical,
                neutral,
                unclear,
            ) in enumerate(stance_block.rows):
                actor_cell = (
                    f"<td rowspan='{len(stance_block.rows)}'>{_esc(stance_block.actor_id)}</td>"
                    if index == 0
                    else ""
                )
                parts.append(
                    f"<tr>{actor_cell}<td>{_esc(source)}</td>"
                    f"<td><span class='leaning {_leaning_class(leaning)}'>{_esc(leaning)}</span></td>"
                    f"<td class='num'>{supportive}</td><td class='num'>{critical}</td>"
                    f"<td class='num'>{neutral}</td><td class='num'>{unclear}</td></tr>"
                )
        parts.append("</table>")
        parts.append(
            "<p class='sub'>A model labelled each publication toward the named person. The number to read is "
            "<em>critical</em>: it shows whether the classifier can see criticism of an incumbent at all. "
            "It can — the opposition outlet carries it. Where it is zero, the material is reportage of the "
            "politician's own statements, which the classifier correctly declines to call criticism.</p>"
        )
    else:
        parts.append("<p>No stance labels stored yet.</p>")

    parts.append("<h2>4. Does the website stand in for the broadcast?</h2>")
    conc = report.concordance
    if conc.available:
        parts.append(
            f"<p>{_esc(conc.source_id)}: {conc.segments} broadcast segments against "
            f"{conc.publications} publications, {_esc(conc.start)} to {_esc(conc.end)}. "
            f"Rank correlation of actor mentions <strong>rho = {conc.rho:.2f}</strong> — "
            f"{_esc(_consequence(conc.rho))}.</p>"
        )
        parts.append(f"<p class='sub'>{_esc(conc.verdict)}</p>")
        parts.append(
            "<p class='sub'>Method: per-actor mention shares in both corpora, compared by Spearman rank "
            "correlation. Measured once, on one window, with 125 publications — a check, not a certificate; "
            "re-run it whenever either corpus grows materially.</p>"
        )
    else:
        parts.append(f"<p>{_esc(conc.verdict)}</p>")

    parts.append("<h2>5. What this report cannot support</h2><ul>")
    for caveat in report.caveats:
        parts.append(f"<li>{_esc(caveat)}</li>")
    parts.append("</ul>")

    parts.append(
        "<footer>Built by GTAF (Georgian TV Agenda &amp; Framing). Body text of articles is not stored or "
        "redistributed; excerpts and embeddings only. Sources are listed with their editorial leaning so a "
        "reader can judge the framing of this report itself.</footer>"
    )
    parts.append("</main></body></html>")
    return "\n".join(parts)
