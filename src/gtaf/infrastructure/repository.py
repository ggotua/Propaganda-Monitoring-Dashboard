"""DuckDB persistence for the collector (SPEC-002 §3.5).

Raw SQL, no ORM: the workload is analytical SQL and a mapping layer would hide it (`tech-stack.md`).
Idempotency is expressed as upsert on natural keys, and each video's cues are replaced inside one
transaction so a re-run converges instead of accumulating.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import duckdb

from gtaf.domain.collector import CaptionCue
from gtaf.domain.models import Channel, Programme, Video


def _utc_now() -> datetime:
    """Return the current UTC instant as a naive datetime (storage convention)."""
    return datetime.now(UTC).replace(tzinfo=None)


class DuckDBRepository:
    """Repository implementation backed by an open DuckDB connection."""

    def __init__(self, conn: duckdb.DuckDBPyConnection) -> None:
        """Initialise the repository.

        Args:
            conn: An open read-write connection (D-005: exactly one writer).
        """
        self._conn = conn

    def upsert_channel(self, channel: Channel) -> None:
        """Insert or update one channel.

        Args:
            channel: Channel to persist.

        Notes:
            No ``ON CONFLICT DO UPDATE``: DuckDB rejects it while child rows reference the row
            (videos and programmes both reference ``channels``). Instead the row is read first and
            written only when something actually differs, which also makes a config-unchanged re-run
            a genuine no-op.
        """
        existing = self._conn.execute(
            "SELECT name_en, name_ka, youtube_handle, youtube_channel_id, active "
            "FROM channels WHERE channel_id = ?",
            [channel.channel_id],
        ).fetchone()

        if existing is None:
            self._conn.execute(
                "INSERT INTO channels "
                "(channel_id, name_en, name_ka, youtube_handle, youtube_channel_id, active) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                [
                    channel.channel_id,
                    channel.name_en,
                    channel.name_ka,
                    channel.youtube_handle,
                    channel.youtube_channel_id,
                    channel.active,
                ],
            )
            return

        resolved_channel_id = channel.youtube_channel_id or existing[3]
        desired = (
            channel.name_en,
            channel.name_ka,
            channel.youtube_handle,
            resolved_channel_id,
            channel.active,
        )
        if tuple(existing) == desired:
            return

        self._conn.execute(
            "UPDATE channels SET name_en = ?, name_ka = ?, youtube_handle = ?, "
            "youtube_channel_id = ?, active = ? WHERE channel_id = ?",
            [
                channel.name_en,
                channel.name_ka,
                channel.youtube_handle,
                resolved_channel_id,
                channel.active,
                channel.channel_id,
            ],
        )

    def upsert_programme(self, programme: Programme) -> None:
        """Insert or update one programme.

        Args:
            programme: Programme to persist.

        Notes:
            Same read-then-write approach as ``upsert_channel``, for the same DuckDB reason.
        """
        patterns = list(programme.title_patterns)
        playlists = list(programme.playlist_ids)
        existing = self._conn.execute(
            "SELECT channel_id, name_en, name_ka, type, title_patterns, playlist_ids, active "
            "FROM programmes WHERE programme_id = ?",
            [programme.programme_id],
        ).fetchone()

        if existing is None:
            self._conn.execute(
                "INSERT INTO programmes "
                "(programme_id, channel_id, name_en, name_ka, type, title_patterns, "
                "playlist_ids, active) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    programme.programme_id,
                    programme.channel_id,
                    programme.name_en,
                    programme.name_ka,
                    programme.type,
                    patterns,
                    playlists,
                    programme.active,
                ],
            )
            return

        desired = (
            programme.channel_id,
            programme.name_en,
            programme.name_ka,
            programme.type,
            patterns,
            playlists,
            programme.active,
        )
        current = (
            existing[0],
            existing[1],
            existing[2],
            existing[3],
            list(existing[4]),
            list(existing[5]),
            existing[6],
        )
        if current == desired:
            return

        self._conn.execute(
            "UPDATE programmes SET channel_id = ?, name_en = ?, name_ka = ?, type = ?, "
            "title_patterns = ?, playlist_ids = ?, active = ? WHERE programme_id = ?",
            [
                programme.channel_id,
                programme.name_en,
                programme.name_ka,
                programme.type,
                patterns,
                playlists,
                programme.active,
                programme.programme_id,
            ],
        )

    def upsert_video(self, video: Video, cues: Sequence[CaptionCue]) -> None:
        """Insert or update one video and replace its cue rows atomically.

        Args:
            video: Video to persist.
            cues: Cues to store; an empty sequence clears any previous rows, which is correct for a
                video whose captions became unavailable.

        Notes:
            Two transactions, and the split is a DuckDB limitation rather than a design choice.
            DuckDB 2.0 enforces FOREIGN KEYs and rejects an UPDATE of a parent row while child rows
            still reference it — and it does not see a same-transaction child delete, so
            "delete then update in one transaction" fails too. Committing the cue deletion first
            makes the video row unreferenced, after which the UPDATE is allowed even when it touches
            the indexed ``channel_id``/``programme_id`` columns.

            The cost is a window in which a crash could leave a video row with its cues
            removed. That is acceptable because it is repairable: the raw payload is already on
            disk (§3.4) and a re-run rewrites both the row and its cues, so the state converges.
        """
        self._conn.execute("BEGIN TRANSACTION")
        try:
            self._conn.execute("DELETE FROM captions WHERE video_id = ?", [video.video_id])
            self._conn.execute("COMMIT")
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

        self._conn.execute("BEGIN TRANSACTION")
        try:
            exists = self._conn.execute(
                "SELECT 1 FROM videos WHERE video_id = ?", [video.video_id]
            ).fetchone()
            if exists:
                self._conn.execute(
                    """
                    UPDATE videos SET
                        channel_id = ?,
                        programme_id = ?,
                        published_at = ?,
                        broadcast_date_local = ?,
                        title = ?,
                        duration_s = ?,
                        caption_kind = ?,
                        caption_lang = ?,
                        status = ?
                    WHERE video_id = ?
                    """,
                    [
                        video.channel_id,
                        video.programme_id,
                        video.published_at,
                        video.broadcast_date_local,
                        video.title,
                        video.duration_s,
                        video.caption_kind,
                        video.caption_lang,
                        video.status,
                        video.video_id,
                    ],
                )
            else:
                self._conn.execute(
                    """
                    INSERT INTO videos
                        (video_id, channel_id, programme_id, published_at,
                         broadcast_date_local, title, duration_s, caption_kind, caption_lang,
                         status, first_seen_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        video.video_id,
                        video.channel_id,
                        video.programme_id,
                        video.published_at,
                        video.broadcast_date_local,
                        video.title,
                        video.duration_s,
                        video.caption_kind,
                        video.caption_lang,
                        video.status,
                        _utc_now(),
                    ],
                )

            if cues:
                self._conn.executemany(
                    "INSERT INTO captions (video_id, idx, start_s, end_s, text) "
                    "VALUES (?, ?, ?, ?, ?)",
                    [
                        (video.video_id, cue.idx, cue.start_s, cue.end_s, cue.text)
                        for cue in cues
                    ],
                )
            self._conn.execute("COMMIT")
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

    def start_run(self, stage: str, params_json: str) -> str:
        """Open a run row.

        Args:
            stage: Pipeline stage name, e.g. ``collect``.
            params_json: JSON of the run parameters.

        Returns:
            The new run id.
        """
        run_id = uuid.uuid4().hex
        self._conn.execute(
            """
            INSERT INTO runs (run_id, stage, params_json, started_at, status)
            VALUES (?, ?, ?, ?, 'running')
            """,
            [run_id, stage, params_json, _utc_now()],
        )
        return run_id

    def finish_run(
        self,
        run_id: str,
        *,
        status: str,
        n_items: int,
        watermark: str | None,
        error: str | None,
    ) -> None:
        """Finalise a run row.

        Args:
            run_id: Run to finalise.
            status: ``ok``, ``failed`` or ``blocked``.
            n_items: Items successfully processed.
            watermark: Newest processed date, ISO-8601, or None.
            error: Error summary when not ``ok``.
        """
        self._conn.execute(
            """
            UPDATE runs
               SET status = ?, finished_at = ?, n_items = ?, watermark = ?, error = ?
             WHERE run_id = ?
            """,
            [status, _utc_now(), n_items, watermark, error, run_id],
        )
