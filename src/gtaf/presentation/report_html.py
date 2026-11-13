"""Self-contained HTML report renderer (SPEC-009).

Pure text generation: `ReportContext` in, one HTML string out. No network, no files, no template engine
— which is also why it can be tested without a browser.

Self-containment is a hard requirement (FR-1): Plotly's JavaScript is inlined once, and nothing in the
output may reference a remote host. Every piece of corpus text is escaped, because topic labels are ASR
keywords and a keyword containing `<` must never become markup (FR-6).
"""

from __future__ import annotations

from html import escape

import plotly.graph_objects as go

from gtaf.application.report import ReportContext
from gtaf.domain.topics import OUTLIER_TOPIC_ID

OUTLIER_COLOUR = "#b23b3b"
CLUSTER_COLOUR = "#3b6ab2"

CSS = """
:root { --ink:#1d232b; --muted:#5b6673; --line:#e2e6eb; --warn:#b23b3b; --accent:#3b6ab2; }
* { box-sizing: border-box; }
body { margin:0; padding:32px; font-family: "Segoe UI", system-ui, sans-serif; color:var(--ink);
       background:#fbfcfd; line-height:1.5; }
main { max-width: 1040px; margin: 0 auto; }
h1 { font-size: 26px; margin:0 0 4px; }
h2 { font-size: 18px; margin:32px 0 8px; }
.sub { color:var(--muted); font-size:14px; margin:0; }
.notice { margin:18px 0; padding:12px 14px; border-left:4px solid var(--warn);
          background:#fdf3f3; font-size:14px; }
.kpis { display:flex; gap:16px; flex-wrap:wrap; margin:18px 0; }
.kpi { flex:1 1 180px; border:1px solid var(--line); border-radius:8px; padding:12px 14px;
       background:#fff; }
.kpi .label { font-size:12px; text-transform:uppercase; letter-spacing:.04em; color:var(--muted); }
.kpi .value { font-size:24px; font-weight:600; margin-top:2px; }
.kpi.warn .value { color:var(--warn); }
table { width:100%; border-collapse:collapse; font-size:14px; background:#fff; }
th, td { text-align:left; padding:7px 10px; border-bottom:1px solid var(--line); vertical-align:top; }
th { font-size:12px; text-transform:uppercase; letter-spacing:.04em; color:var(--muted); }
.method { border-top:1px solid var(--line); margin-top:36px; padding-top:16px; font-size:14px; }
.method li { margin-bottom:6px; }
.empty { padding:24px; border:1px dashed var(--line); border-radius:8px; color:var(--muted); }
footer { margin-top:36px; font-size:12px; color:var(--muted); }
"""


def _topic_figure(context: ReportContext, *, inline_js: bool) -> str:
    """Render the topic distribution chart.

    Args:
        context: Report data.
        inline_js: Whether to inline Plotly's JavaScript (only the first figure needs it).

    Returns:
        An embeddable HTML fragment.
    """
    shares = sorted(context.shares, key=lambda share: share.share)
    labels = [
        escape(
            f"{'UNCLASSIFIED' if share.topic_id == OUTLIER_TOPIC_ID else 't' + str(share.topic_id)}"
            f" · {(share.label or '')[:40]}"
        )
        for share in shares
    ]
    values = [share.share * 100 for share in shares]
    colours = [
        OUTLIER_COLOUR if share.topic_id == OUTLIER_TOPIC_ID else CLUSTER_COLOUR
        for share in shares
    ]
    figure = go.Figure(
        go.Bar(
            x=values,
            y=labels,
            orientation="h",
            marker_color=colours,
            customdata=[share.n_segments for share in shares],
            hovertemplate="%{y}<br>%{x:.1f}% of slice<br>%{customdata} segments<extra></extra>",
        )
    )
    figure.update_layout(
        template="plotly_white",
        height=max(320, 26 * len(labels)),
        margin={"l": 10, "r": 10, "t": 10, "b": 40},
        xaxis_title="share of all segments in the slice (%)",
        yaxis_title="",
    )
    return str(
        figure.to_html(
            full_html=False,
            include_plotlyjs="inline" if inline_js else False,
            config={"displayModeBar": False},
            # Plotly otherwise generates a random div id, which makes two renders of the same data
            # differ (SPEC-009 FR-8).
            div_id="gtaf-topic-chart",
        )
    )


def _coverage_figure(context: ReportContext) -> str:
    """Render the clustered-vs-unclassified chart per channel.

    Args:
        context: Report data.

    Returns:
        An embeddable HTML fragment, or an empty string when there is no coverage data.
    """
    if not context.coverage:
        return ""
    channels = [row[0] for row in context.coverage]
    clustered = [row[1] for row in context.coverage]
    unclassified = [row[2] - row[1] for row in context.coverage]

    figure = go.Figure()
    figure.add_bar(name="clustered", x=channels, y=clustered, marker_color=CLUSTER_COLOUR)
    figure.add_bar(name="unclassified", x=channels, y=unclassified, marker_color=OUTLIER_COLOUR)
    figure.update_layout(
        template="plotly_white",
        barmode="stack",
        height=360,
        margin={"l": 10, "r": 10, "t": 10, "b": 40},
        yaxis_title="segments",
        legend={"orientation": "h"},
    )
    return str(
        figure.to_html(
            full_html=False,
            include_plotlyjs=False,
            config={"displayModeBar": False},
            div_id="gtaf-coverage-chart",
        )
    )


def _period(context: ReportContext) -> str:
    """Describe the reporting period in words.

    Args:
        context: Report data.

    Returns:
        A human-readable period string, falling back to the corpus span when the slice is unbounded —
        "archive start to latest" is vague when the data knows the actual dates.
    """
    since = context.since or context.overview.first_date
    until = context.until or context.overview.last_date
    if since and until:
        return f"{since.isoformat()} to {until.isoformat()}"
    return "period not recorded"


def render_html(context: ReportContext) -> str:
    """Render the full self-contained report.

    Args:
        context: Fully computed report data.

    Returns:
        A complete HTML document with no external references (FR-1).
    """
    versions = ", ".join(context.topic_versions) or "none recorded"
    methods = ", ".join(context.segment_methods) or "none recorded"

    kpis = f"""
    <div class="kpis">
      <div class="kpi"><div class="label">Videos</div><div class="value">{context.overview.videos}</div></div>
      <div class="kpi"><div class="label">Segments</div><div class="value">{context.overview.segments}</div></div>
      <div class="kpi"><div class="label">Topics</div><div class="value">{max(context.overview.topics - 1, 0)}</div></div>
      <div class="kpi warn"><div class="label">Unclassified</div><div class="value">{context.outlier_rate:.1%}</div></div>
    </div>
    """

    if context.is_empty:
        body = (
            '<div class="empty">No classified segments in this slice. '
            "Nothing is charted rather than charting an absence.</div>"
        )
    else:
        rows = "".join(
            "<tr>"
            f"<td>{'UNCLASSIFIED' if share.topic_id == OUTLIER_TOPIC_ID else 't' + str(share.topic_id)}</td>"
            f"<td>{escape(share.label or '')}</td>"
            f"<td>{share.n_segments}</td>"
            f"<td>{share.share:.1%}</td>"
            f"<td>{escape(', '.join(share.keywords[:8]))}</td>"
            "</tr>"
            for share in context.shares
        )
        body = (
            '<h2>Topic distribution</h2>'
            + _topic_figure(context, inline_js=True)
            + "<h2>Clustered vs unclassified, by channel</h2>"
            + _coverage_figure(context)
            + "<h2>Topics in this slice</h2>"
            + '<table><thead><tr><th>Topic</th><th>Label</th><th>Segments</th><th>Share</th>'
            + "<th>Keywords</th></tr></thead><tbody>"
            + rows
            + "</tbody></table>"
        )

    methodology = f"""
    <section class="method">
      <h2>Methodology</h2>
      <ul>
        <li><strong>What this is.</strong> Georgian YouTube captions were collected, merged into
            timestamped sentences, split into 90-second segments, and clustered with BERTopic over
            multilingual sentence embeddings. Every figure above is computed from the database, not
            written by a person.</li>
        <li><strong>Coverage.</strong> {context.overview.videos} videos and
            {context.overview.segments} segments across {context.overview.clusters} channel(s),
            {_period(context)}. A report about part of a period is not a report about a change over
            time.</li>
        <li><strong>Unclassified segments: {context.outlier_rate:.1%}.</strong> This share is the
            denominator problem: a topic at 7% means 7% of <em>all</em> segments in this slice, most of
            which the model did place. Read a share as a share of the channel's output only after
            checking the unclassified rate.</li>
        <li><strong>Labels are keywords, not topic names.</strong> Georgian terms come from the
            clusters' own vocabulary; the English naming step needs the LLM gateway, which is not
            built. A label describes what a cluster contains, not what it means.</li>
        <li><strong>What this is not.</strong> No causal claim, no ranking of channels, no claim about
            intent or reach. Segments are fixed windows and cut across topic boundaries by
            construction.</li>
        <li><strong>Provenance.</strong> Segmentation: {escape(methods)}. Topic method:
            {escape(versions)}. All figures are reproducible with <code>gtaf report</code> against the
            same database.</li>
      </ul>
    </section>
    """

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(context.title)}</title>
<style>{CSS}</style>
</head>
<body>
<main>
  <h1>{escape(context.title)}</h1>
  <p class="sub">{escape(context.channel_label)} · {_period(context)} ·
     generated {context.generated_at.strftime("%Y-%m-%d %H:%M")} UTC</p>
  <p class="notice"><strong>Machine-derived figures.</strong> Every number below is computed by the
     pipeline and is reproducible from the same database. Verify any single claim against the source
     broadcast before using it in a decision.</p>
  {kpis}
  {body}
  {methodology}
  <footer>Generated by GTAF · one self-contained file, no external resources.</footer>
</main>
</body>
</html>
"""
