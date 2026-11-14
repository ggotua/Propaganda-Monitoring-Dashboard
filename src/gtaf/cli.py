"""Command-line entry point and composition root.

This is the only module that wires concrete adapters to use cases (D-004). Exit codes are part of
the contract and are asserted by tests:

===  ==========================================================
0    success
1    unexpected error
2    configuration invalid (FR-4)
3    unsupported schema version (FR-2)
4    database locked by another process (FR-8)
===  ==========================================================
"""

from __future__ import annotations

import argparse
import importlib
import json
import platform
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from gtaf.application.collect import ClientBlockedError, CollectPlan, run_collection
from gtaf.application.config import ConfigError
from gtaf.application.initialize import (
    SchemaVersionError,
    migrate_database,
    read_schema_version,
)
from gtaf.application.report import build_report
from gtaf.application.schedule import (
    DEFAULT_BATCH_LIMIT,
    DEFAULT_DAILY_BUDGET,
    next_batch,
    recent_runs,
)
from gtaf.application.segment import segment_video
from gtaf.application.segment_drift import segment_video_drift
from gtaf.application.text import sentences_for_video
from gtaf.application.topic_labels import label_topics
from gtaf.application.topics import InsufficientDataError, run_topics
from gtaf.domain.invariants import SUPPORTED_SCHEMA_VERSION
from gtaf.domain.llm import (
    PRICES_CHECKED_ON,
    PROVIDER_CHAINS,
    BudgetExceededError,
    LLMError,
    ProviderUnavailableError,
    QuotaExceededError,
)
from gtaf.domain.models import Programme
from gtaf.domain.segment import MAX_S, MIN_S, TARGET_S
from gtaf.infrastructure.config_io import load_configuration
from gtaf.infrastructure.db import (
    DatabaseLockedError,
    DatabaseNotFoundError,
    connect,
    load_migrations,
    open_database,
)
from gtaf.infrastructure.embeddings import SentenceTransformerEmbedder
from gtaf.infrastructure.llm_gateway import Gateway, GatewayConfig, month_start
from gtaf.infrastructure.llm_providers import api_key, build_transport
from gtaf.infrastructure.logging_setup import log_event, setup_logging
from gtaf.infrastructure.raw_store import FileRawStore
from gtaf.infrastructure.repository import DuckDBRepository
from gtaf.infrastructure.topics_bertopic import DEFAULT_MODEL as DEFAULT_TOPIC_MODEL
from gtaf.infrastructure.topics_bertopic import BertopicEngine
from gtaf.infrastructure.youtube import YtDlpSource
from gtaf.presentation.report_html import render_html

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_CONFIG = 2
EXIT_SCHEMA = 3
EXIT_LOCKED = 4
EXIT_BLOCKED = 5

_REQUIRED_IMPORTS: tuple[str, ...] = ("duckdb", "pydantic", "yaml")


def _build_parser() -> argparse.ArgumentParser:
    """Construct the argument parser with all subcommands."""
    parser = argparse.ArgumentParser(
        prog="gtaf", description="Georgian TV Agenda & Framing — pipeline foundation"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    init_db = sub.add_parser("init-db", help="create or verify the database schema")
    init_db.add_argument("path", type=Path, help="database file path")
    init_db.add_argument("--log-dir", type=Path, default=Path("logs"))

    schema_version = sub.add_parser("schema-version", help="print the database schema version")
    schema_version.add_argument("path", type=Path, help="database file path")

    check_config = sub.add_parser("check-config", help="validate the corpus configuration")
    check_config.add_argument("--config-dir", type=Path, default=Path("config"))

    doctor = sub.add_parser("doctor", help="check interpreter and dependencies (FR-12)")
    doctor.add_argument("--json", action="store_true", help="emit a JSON object")
    doctor.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data"),
        help="directory the write probe targets (default: data)",
    )

    collect = sub.add_parser("collect", help="collect videos and captions for in-window videos")
    collect.add_argument("--db", type=Path, default=Path("data/gtaf.duckdb"),
                         help="database file (default: data/gtaf.duckdb)")
    collect.add_argument("--config-dir", type=Path, default=Path("config"))
    collect.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    collect.add_argument("--log-dir", type=Path, default=Path("logs"))
    collect.add_argument("--channel", default=None,
                         help="collect a single channel_id instead of all active channels")
    collect.add_argument("--since", default="2026-10-01", help="earliest publish date (ISO)")
    collect.add_argument("--limit", type=int, default=20,
                         help="maximum videos kept per channel (default: 20)")
    collect.add_argument("--listing-limit", type=int, default=120,
                         help="maximum uploads listed per channel; bounds pagination")
    collect.add_argument("--throttle", type=float, default=2.0,
                         help="seconds to sleep after every network call (default: 2.0)")
    collect.add_argument("--skip-existing", action="store_true",
                         help="do not re-fetch videos already in the database (makes a long "
                              "backfill resumable after an interruption)")

    text = sub.add_parser("text", help="print normalised sentences for one video (read-only)")
    text.add_argument("--video-id", required=True, help="YouTube video id")
    text.add_argument("--db", type=Path, default=Path("data/gtaf.duckdb"))
    text.add_argument("--limit", type=int, default=40, help="sentences to print (default: 40)")

    segment = sub.add_parser("segment", help="segment one video or all videos (fixed or drift)")
    segment.add_argument("--video-id", default=None, help="segment one video")
    segment.add_argument("--all", action="store_true", help="segment every stored video")
    segment.add_argument("--db", type=Path, default=Path("data/gtaf.duckdb"))
    segment.add_argument(
        "--method",
        choices=("fixed", "drift"),
        default="fixed",
        help="fixed windows (control) or drift at semantic boundaries (D-027)",
    )
    segment.add_argument("--target", type=float, default=TARGET_S, help="target window seconds")
    segment.add_argument("--max", type=float, default=MAX_S, help="hard ceiling seconds")
    segment.add_argument("--min", type=float, default=MIN_S, help="minimum trailing remainder")

    topics = sub.add_parser("topics", help="cluster segments into topics (BERTopic, no LLM)")
    topics.add_argument("--db", type=Path, default=Path("data/gtaf.duckdb"))
    topics.add_argument("--log-dir", type=Path, default=Path("logs"))
    topics.add_argument(
        "--model", default=DEFAULT_TOPIC_MODEL, help="sentence-transformers model id"
    )
    topics.add_argument(
        "--min-segments", type=int, default=200, help="refuse to cluster fewer segments"
    )
    topics.add_argument("--top", type=int, default=10, help="topics to print")

    report = sub.add_parser("report", help="write a self-contained HTML report (no Quarto)")
    report.add_argument("--out", type=Path, required=True, help="output .html path")
    report.add_argument("--db", type=Path, default=Path("data/gtaf.duckdb"))
    report.add_argument("--channel", default=None, help="restrict to one channel_id")
    report.add_argument("--since", default=None, help="earliest broadcast date (ISO)")
    report.add_argument("--until", default=None, help="latest broadcast date (ISO)")

    next_cmd = sub.add_parser("next", help="decide what to collect next (read-only)")
    next_cmd.add_argument("--db", type=Path, default=Path("data/gtaf.duckdb"))
    next_cmd.add_argument("--config-dir", type=Path, default=Path("config"))
    next_cmd.add_argument("--budget", type=int, default=DEFAULT_DAILY_BUDGET)
    next_cmd.add_argument("--batch-limit", type=int, default=DEFAULT_BATCH_LIMIT)
    next_cmd.add_argument("--json", action="store_true", help="machine-readable output")

    runs = sub.add_parser("runs", help="show recent runs (read-only)")
    runs.add_argument("--db", type=Path, default=Path("data/gtaf.duckdb"))
    runs.add_argument("--limit", type=int, default=20)

    llm_check = sub.add_parser("llm-check", help="one minimal live call per provider")
    llm_check.add_argument("--db", type=Path, default=Path("data/gtaf.duckdb"))
    llm_check.add_argument("--env-file", type=Path, default=Path(".env"))
    llm_check.add_argument("--budget", type=float, default=None, help="monthly cap in USD")

    llm_bench = sub.add_parser("llm-benchmark", help="same Georgian task on both providers")
    llm_bench.add_argument("--db", type=Path, default=Path("data/gtaf.duckdb"))
    llm_bench.add_argument("--env-file", type=Path, default=Path(".env"))
    llm_bench.add_argument("--limit", type=int, default=3, help="segments to send")
    llm_bench.add_argument("--budget", type=float, default=None, help="monthly cap in USD")
    llm_bench.add_argument("--out", type=Path, default=Path("reports/llm-benchmark.md"))

    label = sub.add_parser("label-topics", help="name topics via the LLM gateway (ka + en)")
    label.add_argument("--db", type=Path, default=Path("data/gtaf.duckdb"))
    label.add_argument("--env-file", type=Path, default=Path(".env"))
    label.add_argument("--provider", default="gemini")
    label.add_argument("--budget", type=float, default=None, help="monthly cap in USD")

    return parser


def _cmd_init_db(path: Path, log_dir: Path) -> int:
    """Create the schema if absent, or migrate it forward (FR-1, FR-2, FR-3)."""
    logger = setup_logging(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)

    conn = connect(path, read_only=False)
    try:
        result = migrate_database(conn, load_migrations())
    finally:
        conn.close()

    if result.applied:
        action = "created" if result.from_version is None else "migrated"
        log_event(
            logger,
            20,
            "db.migrated",
            path=str(path),
            from_version=result.from_version,
            to_version=result.to_version,
            applied=list(result.applied),
        )
        print(
            f"{action} {path} (schema_version={result.to_version}, "
            f"applied {len(result.applied)} migration(s))"
        )
    else:
        log_event(
            logger, 20, "db.opened", path=str(path), schema_version=result.to_version
        )
        print(f"{path} already at schema_version={result.to_version}; nothing to do")
    return EXIT_OK


def _cmd_schema_version(path: Path) -> int:
    """Print the stored schema version, refusing an unsupported one (FR-2)."""
    conn = open_database(path, read_only=True)
    try:
        version = read_schema_version(conn)
    finally:
        conn.close()
    print(version)
    return EXIT_OK


def _cmd_check_config(config_dir: Path) -> int:
    """Validate configuration and report counts (FR-7)."""
    bundle = load_configuration(config_dir)
    print(
        f"configuration OK: {bundle.channel_count} channels, "
        f"{bundle.programme_count} programmes"
    )
    return EXIT_OK


def _cmd_doctor(as_json: bool, data_dir: Path) -> int:
    """Report interpreter and dependency health (FR-12)."""
    import duckdb

    checks: list[dict[str, object]] = []
    python_ok = sys.version_info[:2] >= (3, 12)
    checks.append(
        {
            "name": "python",
            "ok": python_ok,
            "detail": platform.python_version(),
            "required": ">=3.12",
        }
    )

    for module_name in _REQUIRED_IMPORTS:
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:  # noqa: BLE001 - a failed import is the result being reported
            checks.append(
                {"name": module_name, "ok": False, "detail": f"{type(exc).__name__}: {exc}",
                 "required": "importable"}
            )
        else:
            checks.append(
                {
                    "name": module_name,
                    "ok": True,
                    "detail": str(getattr(module, "__version__", "version unknown")),
                    "required": "importable",
                }
            )

    probe_ok, probe_detail = _write_probe(data_dir)
    checks.append({"name": "db_write_probe", "ok": probe_ok, "detail": probe_detail,
                   "required": "can create a database file"})

    ok = all(bool(check["ok"]) for check in checks)

    if as_json:
        import json

        print(json.dumps({"ok": ok, "duckdb": duckdb.__version__, "checks": checks}, indent=2))
    else:
        for check in checks:
            mark = "OK  " if check["ok"] else "FAIL"
            detail = check["detail"]
            required = check["required"]
            print(f"  [{mark}] {check['name']:<16} {detail}  (required: {required})")
        print(f"\nVERDICT: {'healthy' if ok else 'problems found'}")
    return EXIT_OK if ok else EXIT_ERROR


def _write_probe(probe_dir: Path) -> tuple[bool, str]:
    """Create and drop a throwaway database where real data will live.

    Probing the project's data directory rather than the OS temp directory is deliberate: a
    machine can have a writable temp dir and an unwritable data dir (or the reverse), and only
    the latter determines whether the pipeline can run. It also avoids reporting a sandboxed
    temp directory as a database problem.

    Args:
        probe_dir: Directory to create and remove the probe database in.

    Returns:
        A ``(ok, detail)`` pair suitable for a doctor check row.
    """
    import duckdb

    probe = probe_dir / "_doctor_probe.duckdb"
    try:
        probe_dir.mkdir(parents=True, exist_ok=True)
        conn = duckdb.connect(str(probe))
        try:
            conn.execute("CREATE TABLE t (x INTEGER)")
        finally:
            conn.close()
        probe.unlink(missing_ok=True)
        return True, f"created and removed a database in {probe_dir}"
    except Exception as exc:  # noqa: BLE001 - the probe exists to catch any failure
        return False, f"{type(exc).__name__}: {exc}"
    finally:
        probe.unlink(missing_ok=True)


def _cmd_collect(
    *,
    config_dir: Path,
    db_path: Path,
    raw_dir: Path,
    log_dir: Path,
    channel: str | None,
    since: str,
    limit: int,
    listing_limit: int,
    throttle: float,
    skip_existing: bool = False,
) -> int:
    """Collect in-window videos and captions, then print a coverage report (FR-10, §3.7).

    Args:
        config_dir: Directory holding the corpus configuration.
        db_path: Database file.
        raw_dir: Root for immutable raw payloads.
        log_dir: Directory for the JSON log.
        channel: Restrict to one ``channel_id``, or None for all active channels.
        since: Earliest publish date, ISO-8601.
        limit: Maximum videos kept per channel.
        listing_limit: Maximum uploads listed per channel.
        throttle: Seconds to sleep after every network call.

    Returns:
        Process exit code.
    """
    logger = setup_logging(log_dir)
    bundle = load_configuration(config_dir)

    channels = [candidate for candidate in bundle.channels if candidate.active]
    if channel is not None:
        channels = [candidate for candidate in channels if candidate.channel_id == channel]
        if not channels:
            raise ConfigError([f"--channel '{channel}' is not an active configured channel"])

    programmes_by_channel: dict[str, list[Programme]] = {}
    for programme in bundle.programmes:
        programmes_by_channel.setdefault(programme.channel_id, []).append(programme)

    conn = connect(db_path, read_only=False)
    try:
        version = read_schema_version(conn)
        if version != SUPPORTED_SCHEMA_VERSION:
            raise SchemaVersionError(version, SUPPORTED_SCHEMA_VERSION)
        plan = CollectPlan(
            since=date.fromisoformat(since),
            limit=limit,
            listing_limit=listing_limit,
            skip_existing=skip_existing,
        )
        result = run_collection(
            channels,
            programmes_by_channel,
            plan,
            source=YtDlpSource(throttle=throttle),
            repo=DuckDBRepository(conn),
            raw_store=FileRawStore(raw_dir),
            logger=logger,
        )
    finally:
        conn.close()

    print(f"run {result.run_id}: {result.status}")
    header = (
        f"{'channel':<22}{'listed':>7}{'kept':>6}{'capt':>6}{'nocap':>7}"
        f"{'unclass':>9}{'skip':>6}{'had':>6}"
    )
    print(header)
    print("-" * len(header))
    for report in result.reports:
        print(
            f"{report.name_en[:21]:<22}{report.listed:>7}{report.kept:>6}"
            f"{report.captioned:>6}{report.no_caption:>7}{report.unclassified:>9}"
            f"{report.skipped:>6}{report.already_present:>6}"
        )
    return EXIT_OK


def _cmd_text(video_id: str, db_path: Path, limit: int) -> int:
    """Print normalised sentences for one video (FR-8).

    Args:
        video_id: YouTube video id.
        db_path: Database file, opened read-only.
        limit: Maximum sentences to print.

    Returns:
        Process exit code.
    """
    conn = open_database(db_path, read_only=True)
    try:
        result = sentences_for_video(video_id, DuckDBRepository(conn))
    finally:
        conn.close()

    if not result.sentences:
        print(f"{video_id}: no sentences (no captions, or nothing after normalisation)")
        return EXIT_OK

    print(
        f"{video_id}: {len(result.sentences)} sentences, {result.n_events} non-speech events, "
        f"{result.n_flagged} flagged (normaliser v{result.version})"
    )
    for sentence in result.sentences[:limit]:
        flags = f" [{','.join(sentence.flags)}]" if sentence.flags else ""
        print(
            f"{sentence.start_s:7.1f}-{sentence.end_s:7.1f} t{sentence.turn_index:<3}{flags} "
            f"{sentence.text}"
        )
    return EXIT_OK


def _cmd_segment(
    *,
    db_path: Path,
    video_id: str | None,
    segment_all: bool,
    target_s: float,
    max_s: float,
    min_s: float,
    log_dir: Path,
    method: str = "fixed",
) -> int:
    """Segment one video or all videos (SPEC-004 fixed, SPEC-006 drift).

    Args:
        db_path: Database file, opened read-write.
        video_id: Single video to segment, or None.
        segment_all: Segment every stored video.
        target_s: Window length to aim for.
        max_s: Hard ceiling per segment.
        min_s: Minimum trailing remainder.
        log_dir: Directory for the JSON log.
        method: ``fixed`` or ``drift`` (D-027).

    Returns:
        Process exit code.
    """
    if not video_id and not segment_all:
        print("specify --video-id or --all", file=sys.stderr)
        return EXIT_CONFIG

    logger = setup_logging(log_dir)
    conn = connect(db_path, read_only=False)
    try:
        version = read_schema_version(conn)
        if version != SUPPORTED_SCHEMA_VERSION:
            raise SchemaVersionError(version, SUPPORTED_SCHEMA_VERSION)
        repo = DuckDBRepository(conn)
        targets = (video_id,) if video_id else repo.list_video_ids()
        total = 0
        empty = 0
        embedder = SentenceTransformerEmbedder() if method == "drift" else None
        for target in targets:
            if embedder is None:
                written = segment_video(
                    target, repo, repo, target_s=target_s, max_s=max_s, min_s=min_s
                )
            else:
                written = segment_video_drift(target, repo, repo, embedder)
            total += written
            if written == 0:
                empty += 1
        log_event(
            logger, 20, "segment.done", videos=len(targets), segments=total, empty=empty,
            method=method,
        )
    finally:
        conn.close()

    print(f"segmented {len(targets)} video(s) with {method}: {total} segments, {empty} with none")
    return EXIT_OK


def _cmd_topics(
    *, db_path: Path, log_dir: Path, model: str, min_segments: int, top: int
) -> int:
    """Cluster segments into topics and persist the assignments (SPEC-007 FR-1…FR-7).

    Args:
        db_path: Database file, opened read-write.
        log_dir: Directory for the JSON log.
        model: Sentence-transformers model id.
        min_segments: Refuse below this many segments.
        top: How many topics to print.

    Returns:
        Process exit code.
    """
    logger = setup_logging(log_dir)
    conn = connect(db_path, read_only=False)
    try:
        version = read_schema_version(conn)
        if version != SUPPORTED_SCHEMA_VERSION:
            raise SchemaVersionError(version, SUPPORTED_SCHEMA_VERSION)
        repo = DuckDBRepository(conn)
        engine = BertopicEngine(model)
        result = run_topics(repo, engine, repo, min_segments=min_segments)
        topic_rows = conn.execute(
            "SELECT topic_id, n_segments, label_ka, keywords FROM topics "
            "WHERE run_id = ? ORDER BY n_segments DESC LIMIT ?",
            [result.run_id, top],
        ).fetchall()
    finally:
        conn.close()

    log_event(
        logger,
        20,
        "topics.done",
        run_id=result.run_id,
        segments=result.n_segments,
        topics=result.n_topics,
        outliers=result.n_outliers,
        outlier_rate=round(result.outlier_rate, 4),
        method_version=result.method_version,
    )

    print(f"run {result.run_id}: {result.method_version}")
    print(
        f"segments {result.n_segments} | topics {result.n_topics} | "
        f"outliers {result.n_outliers} ({result.outlier_rate:.1%})"
    )
    print("\n  topic  size  label / keywords")
    for topic_id, n_segments, label, keywords in topic_rows:
        marker = "OUTLIER" if int(topic_id) == -1 else f"t{topic_id}"
        terms = ", ".join(list(keywords)[:8]) if keywords else (label or "")
        print(f"  {marker:>7} {int(n_segments):>5}  {terms}")
    return EXIT_OK


def _cmd_report(
    *, db_path: Path, out_path: Path, channel: str | None, since: str | None, until: str | None
) -> int:
    """Write a self-contained HTML report for a slice (SPEC-009).

    Args:
        db_path: Database file, opened read-only.
        out_path: Destination HTML file.
        channel: Restrict to one channel id, or None.
        since: Earliest broadcast date, ISO-8601, or None.
        until: Latest broadcast date, ISO-8601, or None.

    Returns:
        Process exit code.
    """
    conn = open_database(db_path, read_only=True)
    try:
        context = build_report(
            conn,
            channel_id=channel,
            since=date.fromisoformat(since) if since else None,
            until=date.fromisoformat(until) if until else None,
        )
    finally:
        conn.close()

    html = render_html(context)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")

    if context.is_empty:
        print(f"wrote {out_path} — slice is empty, the report says so rather than charting nothing")
    else:
        print(
            f"wrote {out_path} ({len(html):,} bytes) — {len(context.shares)} topic(s), "
            f"unclassified {context.outlier_rate:.1%}"
        )
    return EXIT_OK


def _cmd_next(
    *, db_path: Path, config_dir: Path, budget: int, batch_limit: int, as_json: bool
) -> int:
    """Decide whether to collect now, from which channel, and how many (SPEC-010 §2).

    Args:
        db_path: Database file, opened read-only.
        config_dir: Corpus configuration, the source of the channel population.
        budget: Daily video budget.
        batch_limit: Preferred batch size.
        as_json: Emit a JSON object for the scheduled script.

    Returns:
        Process exit code: always 0 unless the database or config cannot be read.
    """
    bundle = load_configuration(config_dir)
    configured = [
        (channel.channel_id, channel.name_en) for channel in bundle.channels if channel.active
    ]
    conn = open_database(db_path, read_only=True)
    try:
        decision = next_batch(conn, configured, budget=budget, batch_limit=batch_limit)
    finally:
        conn.close()

    if as_json:
        print(
            json.dumps(
                {
                    "collect": decision.collect,
                    "channel_id": decision.channel_id,
                    "limit": decision.limit,
                    "collected_today": decision.collected_today,
                    "budget": decision.budget,
                    "reason": decision.reason,
                }
            )
        )
        return EXIT_OK

    print("collect" if decision.collect else "wait")
    print(f"reason: {decision.reason}")
    if decision.collect:
        print(f"channel: {decision.channel_id}  limit: {decision.limit}")
        print(
            f"run: gtaf collect --channel {decision.channel_id} "
            f"--limit {decision.limit} --skip-existing"
        )
    return EXIT_OK


def _cmd_runs(*, db_path: Path, limit: int) -> int:
    """Print recent runs, newest first (SPEC-010 §4).

    Args:
        db_path: Database file, opened read-only.
        limit: Maximum rows.

    Returns:
        Process exit code.
    """
    conn = open_database(db_path, read_only=True)
    try:
        rows = recent_runs(conn, limit=limit)
    finally:
        conn.close()

    if not rows:
        print("no runs recorded")
        return EXIT_OK

    print(f"{'started':<20}{'stage':<10}{'status':<9}{'items':>6}  run")
    for run_id, stage, status, started_at, n_items, watermark, error in rows:
        started = str(started_at)[:19]
        marker = "!" if status in {"failed", "blocked"} else " "
        items = n_items if isinstance(n_items, int) else int(str(n_items))
        print(f"{started:<20}{stage!s:<10}{status!s:<9}{items:>6} {marker} {str(run_id)[:8]}")
        if error:
            print(f"{'':<48}{str(error)[:90]}")
        if watermark:
            print(f"{'':<48}watermark {watermark}")
    return EXIT_OK


def _gateway(conn: object, env_file: Path, budget: float | None) -> Gateway:
    """Build a gateway with every provider whose key is present.

    Args:
        conn: Open read-write connection (the gateway writes `llm_calls`).
        env_file: Path to `.env`.
        budget: Monthly cap in USD, or None for the default.

    Returns:
        A configured gateway.
    """
    repo = DuckDBRepository(conn)  # type: ignore[arg-type]
    transports: dict[str, object] = {}
    for provider in ("gemini", "deepseek"):
        try:
            transports[provider] = build_transport(provider, env_file)
        except LLMError as exc:
            print(f"  {provider}: unavailable — {exc}", file=sys.stderr)
    resolved = budget if budget is not None else _budget_from_env(env_file)
    return Gateway(
        transports,  # type: ignore[arg-type]
        repo,
        config=GatewayConfig(monthly_budget_usd=resolved),
        chains=PROVIDER_CHAINS,
    )


def _budget_from_env(env_file: Path) -> float:
    """Read the monthly budget from the environment or `.env`.

    Args:
        env_file: Path to `.env`.

    Returns:
        Budget in USD, defaulting to 20.
    """
    raw = api_key("GTAF_MONTHLY_BUDGET_USD", env_file)
    try:
        return float(raw) if raw else 20.0
    except ValueError:
        return 20.0


def _cmd_llm_check(*, db_path: Path, env_file: Path, budget: float | None) -> int:
    """Make one minimal live call per provider and report tokens and cost (SPEC-005 FR-7).

    Args:
        db_path: Database file, opened read-write for the call log.
        env_file: Path to `.env`.
        budget: Monthly cap in USD, or None.

    Returns:
        Process exit code: 0 when at least one provider answered.
    """
    print(f"prices checked on {PRICES_CHECKED_ON.isoformat()}")
    conn = connect(db_path, read_only=False)
    try:
        gateway = _gateway(conn, env_file, budget)
        answered = 0
        for provider in ("gemini", "deepseek"):
            try:
                response = gateway.ask(
                    "Reply with the single word OK.", prompt_version="probe-v1", provider=provider
                )
            except BudgetExceededError as exc:
                print(f"  {provider:9} budget refused: {exc}")
            except QuotaExceededError as exc:
                print(f"  {provider:9} quota exhausted: {exc}")
            except (ProviderUnavailableError, LLMError) as exc:
                print(f"  {provider:9} failed: {exc}")
            else:
                answered += 1
                cached = " (cached)" if response.cached else ""
                tokens = (
                    f"{response.usage.input_tokens}/{response.usage.output_tokens}"
                    f"/{response.usage.total_tokens}"
                )
                print(
                    f"  {provider:9} ok  model={response.model} tokens={tokens} "
                    f"cost=${response.cost_usd:.6f}{cached} "
                    f"tier={response.service_tier or 'n/a'} "
                    f"reply={response.text.strip()[:20]!r}"
                )
        spent = DuckDBRepository(conn).spent_between(month_start())
        print(f"spent this month: ${spent:.6f}")
    finally:
        conn.close()
    return EXIT_OK if answered else EXIT_ERROR


@dataclass(frozen=True, slots=True)
class _BenchRow:
    """One provider response in the benchmark table."""

    segment: str
    provider: str
    model: str
    tokens: int
    cost: float
    cached: bool
    text: str


def _cmd_llm_benchmark(
    *, db_path: Path, env_file: Path, limit: int, budget: float | None, out_path: Path
) -> int:
    """Send the same Georgian labelling task to both providers (SPEC-005 §2).

    Args:
        db_path: Database file.
        env_file: Path to `.env`.
        limit: Number of segments to send.
        budget: Monthly cap in USD, or None.
        out_path: Where to write the comparison for human judgement.

    Returns:
        Process exit code.
    """
    conn = connect(db_path, read_only=False)
    try:
        repo = DuckDBRepository(conn)
        segments = repo.list_segments()[:limit]
        gateway = _gateway(conn, env_file, budget)
        rows: list[_BenchRow] = []
        for index, (segment_id, text) in enumerate(segments, start=1):
            prompt = (
                "შენ ხარ ქართული ტელევიზიის სიახლეების ანალიტიკოსი. მოცემული ტექსტისთვის "
                "შეადგინე ერთი მოკლე თემის სათაური ქართულად (მაქსიმუმ 6 სიტყვა). "
                'უპასუხე მხოლოდ JSON-ით: {"label_ka": "..."}\n\n'
                f"ტექსტი:\n{text[:600]}"
            )
            for provider in ("gemini", "deepseek"):
                try:
                    response = gateway.ask(
                        prompt, prompt_version="label-v1", provider=provider
                    )
                    rows.append(
                        _BenchRow(
                            segment=segment_id,
                            provider=provider,
                            model=response.model,
                            tokens=response.usage.total_tokens,
                            cost=response.cost_usd,
                            cached=response.cached,
                            text=response.text.strip()[:200],
                        )
                    )
                except LLMError as exc:
                    rows.append(
                        _BenchRow(
                            segment=segment_id,
                            provider=provider,
                            model="-",
                            tokens=0,
                            cost=0.0,
                            cached=False,
                            text=f"FAILED: {exc}",
                        )
                    )
            print(f"  [{index}/{len(segments)}] {segment_id} done")
    finally:
        conn.close()

    generated = datetime.now(UTC).strftime("%Y-%m-%d %H:%M")
    lines = [
        "# LLM-BENCHMARK — same Georgian labelling task, two vendors",
        "",
        f"Generated {generated} UTC over {len(segments)} segments.",
        "",
        "Judge the labels by eye: the numbers are objective, the quality is not. "
        "A model that returns valid JSON with a useless label is worse than one that explains "
        "itself.",
        "",
        "| segment | provider | model | tokens | cost USD | cached | label |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        text = row.text.replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| {row.segment} | {row.provider} | {row.model} | {row.tokens} | "
            f"{row.cost:.6f} | {row.cached} | {text} |"
        )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    total = sum(row.cost for row in rows)
    print(f"wrote {out_path}; {len(rows)} responses, total cost ${total:.6f}")
    return EXIT_OK


def _cmd_label_topics(
    *, db_path: Path, env_file: Path, provider: str, budget: float | None
) -> int:
    """Give every topic a Georgian and English name through the gateway.

    Args:
        db_path: Database file, opened read-write.
        env_file: Path to `.env`.
        provider: Provider key to call.
        budget: Monthly cap in USD, or None.

    Returns:
        Process exit code.
    """
    conn = connect(db_path, read_only=False)
    try:
        repo = DuckDBRepository(conn)
        gateway = _gateway(conn, env_file, budget)
        result = label_topics(gateway, repo, provider=provider)
        rows = repo.list_topics(result.run_id)
    finally:
        conn.close()

    print(
        f"run {result.run_id}: {result.labelled} topic(s) named, "
        f"{result.skipped} left with keywords"
    )
    print("\n  topic  size  ka / en")
    for topic_id, label_ka, keywords, n_segments in rows[:12]:
        marker = "OUTLIER" if topic_id == -1 else f"t{topic_id}"
        english = "" if not label_ka else f"  [{label_ka}]"
        print(f"  {marker:>7} {n_segments:>5}{english}")
        if keywords:
            print(f"  {'':>13}{', '.join(keywords[:6])}")
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI.

    Args:
        argv: Arguments without the program name; defaults to ``sys.argv[1:]``.

    Returns:
        Process exit code.
    """
    # This tool prints Georgian text. A Windows console in a legacy code page raises
    # UnicodeEncodeError on the first Georgian character, which turned a working command into exit
    # 1 with a traceback. Reconfigure once, with replacement, so unprintable characters degrade
    # instead of killing the command — the data is never altered, only its terminal rendering.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")

    args = _build_parser().parse_args(argv)
    try:
        if args.command == "init-db":
            return _cmd_init_db(args.path, args.log_dir)
        if args.command == "schema-version":
            return _cmd_schema_version(args.path)
        if args.command == "check-config":
            return _cmd_check_config(args.config_dir)
        if args.command == "doctor":
            return _cmd_doctor(args.json, args.data_dir)
        if args.command == "text":
            return _cmd_text(args.video_id, args.db, args.limit)
        if args.command == "segment":
            return _cmd_segment(
                db_path=args.db,
                video_id=args.video_id,
                segment_all=args.all,
                target_s=args.target,
                max_s=args.max,
                min_s=args.min,
                log_dir=Path("logs"),
                method=args.method,
            )
        if args.command == "topics":
            return _cmd_topics(
                db_path=args.db,
                log_dir=args.log_dir,
                model=args.model,
                min_segments=args.min_segments,
                top=args.top,
            )
        if args.command == "report":
            return _cmd_report(
                db_path=args.db,
                out_path=args.out,
                channel=args.channel,
                since=args.since,
                until=args.until,
            )
        if args.command == "next":
            return _cmd_next(
                db_path=args.db,
                config_dir=args.config_dir,
                budget=args.budget,
                batch_limit=args.batch_limit,
                as_json=args.json,
            )
        if args.command == "runs":
            return _cmd_runs(db_path=args.db, limit=args.limit)
        if args.command == "llm-check":
            return _cmd_llm_check(
                db_path=args.db, env_file=args.env_file, budget=args.budget
            )
        if args.command == "llm-benchmark":
            return _cmd_llm_benchmark(
                db_path=args.db,
                env_file=args.env_file,
                limit=args.limit,
                budget=args.budget,
                out_path=args.out,
            )
        if args.command == "label-topics":
            return _cmd_label_topics(
                db_path=args.db,
                env_file=args.env_file,
                provider=args.provider,
                budget=args.budget,
            )
        if args.command == "collect":
            return _cmd_collect(                config_dir=args.config_dir,
                db_path=args.db,
                raw_dir=args.raw_dir,
                log_dir=args.log_dir,
                channel=args.channel,
                since=args.since,
                limit=args.limit,
                listing_limit=args.listing_limit,
                throttle=args.throttle,
                skip_existing=args.skip_existing,
            )
    except ConfigError as exc:
        for violation in exc.violations:
            print(f"  - {violation}", file=sys.stderr)
        print(f"configuration invalid: {len(exc.violations)} problem(s)", file=sys.stderr)
        return EXIT_CONFIG
    except SchemaVersionError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_SCHEMA
    except DatabaseLockedError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_LOCKED
    except DatabaseNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_ERROR
    except ClientBlockedError as exc:
        # The run row has already been marked 'blocked' in the database (SPEC-002 FR-7).
        print(f"blocked: {exc}", file=sys.stderr)
        return EXIT_BLOCKED
    except InsufficientDataError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_CONFIG
    except Exception as exc:  # noqa: BLE001 - top-level guard; anything else is exit 1
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_ERROR

    print(f"unknown command: {args.command}", file=sys.stderr)
    return EXIT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
