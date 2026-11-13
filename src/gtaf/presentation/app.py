"""Streamlit workbench v1 (SPEC-008).

Read-only by design (D-005). All analytical work lives in `gtaf.application.queries`, which is tested
without Streamlit; this module only renders.

Run with:
    streamlit run src/gtaf/presentation/app.py
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import duckdb
import plotly.graph_objects as go
import streamlit as st

from gtaf.application import queries
from gtaf.domain.topics import OUTLIER_TOPIC_ID
from gtaf.infrastructure.db import DatabaseLockedError, DatabaseNotFoundError, connect

DEFAULT_DB = Path(os.environ.get("GTAF_DB", "data/gtaf.duckdb"))
OUTLIER_COLOUR = "#b23b3b"
CLUSTER_COLOUR = "#3b6ab2"


def _open_read_only() -> duckdb.DuckDBPyConnection:
    """Open the database read-only, or stop the page with a legible message.

    Returns:
        An open read-only connection.

    Notes:
        D-014: collection holds an exclusive lock, so a running collector makes this impossible. The
        user must see "collection in progress", not a raw IO error (FR-7).
    """
    if not DEFAULT_DB.exists():
        st.error(
            f"No database at `{DEFAULT_DB}`. Run `gtaf collect` first, or set `GTAF_DB` to another path."
        )
        st.stop()
    try:
        return connect(DEFAULT_DB, read_only=True)
    except (DatabaseLockedError, DatabaseNotFoundError):
        st.warning(
            "**Collection in progress** — the database is locked by the collector. "
            "No analysis can run until it finishes; this page does not retry."
        )
        st.stop()
    except Exception as exc:  # noqa: BLE001 - surfaced to the user, not swallowed
        st.error(f"Cannot open the database: {exc}")
        st.stop()


def _topic_bar(shares: tuple[queries.TopicShare, ...]) -> go.Figure:
    """Build the topic distribution bar chart.

    Args:
        shares: Topic shares for the current slice.

    Returns:
        A horizontal bar chart where the outlier bucket is visually distinct (FR-3, FR-4).
    """
    ordered = sorted(shares, key=lambda item: item.share)
    labels = [
        f"{'UNCLASSIFIED' if share.topic_id == OUTLIER_TOPIC_ID else 't' + str(share.topic_id)}"
        f" · {share.label[:40]}"
        for share in ordered
    ]
    values = [share.share * 100 for share in ordered]
    counts = [share.n_segments for share in ordered]
    colours = [
        OUTLIER_COLOUR if share.topic_id == OUTLIER_TOPIC_ID else CLUSTER_COLOUR
        for share in ordered
    ]

    figure = go.Figure(
        go.Bar(
            x=values,
            y=labels,
            orientation="h",
            marker_color=colours,
            customdata=counts,
            hovertemplate="%{y}<br>%{x:.1f}% of slice<br>%{customdata} segments<extra></extra>",
        )
    )
    figure.update_layout(
        xaxis_title="share of all segments in the slice (%)",
        yaxis_title="",
        height=max(320, 26 * len(labels)),
        margin={"l": 10, "r": 10, "t": 10, "b": 10},
    )
    return figure


def _coverage_bar(rows: tuple[tuple[str, int, int], ...]) -> go.Figure:
    """Build the per-channel clustered-vs-unclassified chart.

    Args:
        rows: ``(channel, clustered, total)`` triples.

    Returns:
        A stacked bar chart making the outlier share visible per channel (FR-3).
    """
    channels = [row[0] for row in rows]
    clustered = [row[1] for row in rows]
    unclassified = [row[2] - row[1] for row in rows]

    figure = go.Figure()
    figure.add_bar(name="clustered", x=channels, y=clustered, marker_color=CLUSTER_COLOUR)
    figure.add_bar(
        name="unclassified", x=channels, y=unclassified, marker_color=OUTLIER_COLOUR
    )
    figure.update_layout(
        barmode="stack",
        yaxis_title="segments",
        height=360,
        margin={"l": 10, "r": 10, "t": 10, "b": 10},
    )
    return figure


def main() -> None:
    """Render the workbench."""
    st.set_page_config(page_title="GTAF — agenda & framing", layout="wide")
    st.title("Georgian TV agenda & framing")
    st.caption(
        "Machine-derived figures. Every share is computed over **all** segments in the slice, "
        "including those the topic model could not classify."
    )

    conn = _open_read_only()
    try:
        overview = queries.corpus_overview(conn)
        if overview.videos == 0:
            st.info("The database is empty. Collect and segment video first.")
            st.stop()

        channels = queries.channel_options(conn)
        with st.sidebar:
            st.header("Slice")
            names = ["All channels"] + [option.name_en for option in channels]
            chosen = st.selectbox("Channel", names)
            selected_channel = None if chosen == "All channels" else next(
                option.channel_id for option in channels if option.name_en == chosen
            )
            since_default = overview.first_date or date(2026, 10, 1)
            until_default = overview.last_date or date(2026, 11, 30)
            span = st.date_input(
                "Broadcast date range", value=(since_default, until_default)
            )
            since: date | None = None
            until: date | None = None
            if isinstance(span, tuple) and len(span) == 2:
                since, until = span

        shares = queries.topic_shares(
            conn, channel_id=selected_channel, since=since, until=until
        )

        outlier = next((s for s in shares if s.topic_id == OUTLIER_TOPIC_ID), None)
        outlier_rate = outlier.share if outlier else 0.0

        columns = st.columns(4)
        columns[0].metric("Videos", overview.videos)
        columns[1].metric("Segments", overview.segments)
        columns[2].metric("Topics", max(overview.topics - 1, 0))
        columns[3].metric(
            "Unclassified",
            f"{outlier_rate:.1%}",
            help="Share of segments the topic model could not place. This is why shares never sum to a "
            "meaningful 100 % on their own.",
        )

        if not shares:
            st.warning("No classified segments in this slice — nothing to chart yet.")
            st.stop()

        st.subheader("Topic distribution")
        st.plotly_chart(_topic_bar(shares), width="stretch")

        st.subheader("Clustered vs unclassified, by channel")
        st.plotly_chart(_coverage_bar(queries.topic_share_by_channel(conn)), width="stretch")

        st.subheader("Topics in this slice")
        st.dataframe(
            [
                {
                    # Both branches are strings: a column mixing int and str breaks Arrow serialisation.
                    "topic": "UNCLASSIFIED"
                    if share.topic_id == OUTLIER_TOPIC_ID
                    else str(share.topic_id),
                    "segments": share.n_segments,
                    "share": f"{share.share:.1%}",
                    "keywords": ", ".join(share.keywords[:8]),
                }
                for share in shares
            ],
            width="stretch",
            hide_index=True,
        )

        with st.expander("Methodology and caveats"):
            st.markdown(
                f"""
**What this is.** Segments are {90}-second windows of Georgian ASR captions, clustered with BERTopic
over multilingual embeddings. Method version is recorded per run in `runs` and `res_topics`.

**What it is not.**
- Labels are **keywords**, not human-readable topic names. An English label needs the LLM gateway,
  which does not exist yet.
- **{outlier_rate:.1%} of segments in this slice are unclassified.** A topic at 7 % describes this
  slice's 100 % of segments as the denominator, most of which the model placed; but if you read a share
  as "share of the channel's output", multiply by the clustered fraction first.
- The corpus currently covers {overview.clusters} channel(s) from {overview.first_date} to
  {overview.last_date}. This is not a national picture.
- Fixed-window segments cut across topic boundaries by construction; real segmentation is SPEC-006.

See `docs/TOPIC-EVAL.md` §3 for the validity review and §4 for what may not be claimed.
"""
            )
    finally:
        conn.close()


main()
