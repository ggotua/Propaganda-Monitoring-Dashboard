-- 001_init.sql — initial schema (SPEC-001 §5.1).
--
-- RULES: this file is append-only once it has run against a non-throwaway database. Changes go
-- in 002_*.sql. The migration runner splits statements on the semicolon character, so a
-- statement must not contain one inside a literal. Comments must be full-line: a trailing
-- comment after a statement is not supported by the runner.
--
-- Time convention (D-009): instants are UTC, naive TIMESTAMP; Tbilisi local dates are separate
-- DATE columns derived at ingest.

CREATE TABLE schema_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

INSERT INTO schema_meta (key, value) VALUES ('schema_version', '1');

CREATE TABLE channels (
    channel_id         TEXT PRIMARY KEY,
    name_en            TEXT NOT NULL,
    name_ka            TEXT,
    youtube_handle     TEXT NOT NULL UNIQUE,
    youtube_channel_id TEXT,
    active             BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE programmes (
    programme_id   TEXT PRIMARY KEY,
    channel_id     TEXT NOT NULL REFERENCES channels(channel_id),
    name_en        TEXT NOT NULL,
    name_ka        TEXT,
    type           TEXT NOT NULL CHECK (type IN ('news', 'talk', 'interview')),
    title_patterns TEXT[] NOT NULL DEFAULT [],
    playlist_ids   TEXT[] NOT NULL DEFAULT [],
    active         BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE videos (
    video_id             TEXT PRIMARY KEY,
    channel_id           TEXT NOT NULL REFERENCES channels(channel_id),
    programme_id         TEXT REFERENCES programmes(programme_id),
    published_at         TIMESTAMP NOT NULL,
    broadcast_date_local DATE NOT NULL,
    title                TEXT NOT NULL,
    duration_s           INTEGER CHECK (duration_s >= 0),
    caption_kind         TEXT NOT NULL CHECK (caption_kind IN ('manual', 'auto', 'none')),
    caption_lang         TEXT NOT NULL DEFAULT '',
    status               TEXT NOT NULL CHECK (status IN ('pending', 'captioned', 'skipped_no_caption', 'failed')),
    first_seen_at        TIMESTAMP NOT NULL
);

CREATE INDEX idx_videos_channel_date ON videos(channel_id, broadcast_date_local);

CREATE INDEX idx_videos_programme ON videos(channel_id, programme_id);

CREATE TABLE captions (
    video_id TEXT NOT NULL REFERENCES videos(video_id),
    idx      INTEGER NOT NULL CHECK (idx >= 0),
    start_s  REAL NOT NULL CHECK (start_s >= 0),
    end_s    REAL NOT NULL,
    text     TEXT NOT NULL,
    PRIMARY KEY (video_id, idx),
    CHECK (end_s > start_s)
);

CREATE INDEX idx_captions_video ON captions(video_id, idx);

CREATE TABLE segments (
    segment_id  TEXT PRIMARY KEY,
    video_id    TEXT NOT NULL REFERENCES videos(video_id),
    start_s     REAL NOT NULL CHECK (start_s >= 0),
    end_s       REAL NOT NULL,
    text        TEXT NOT NULL,
    title_ka    TEXT,
    title_en    TEXT,
    seg_method  TEXT NOT NULL CHECK (seg_method IN ('llm', 'texttiling', 'fixed')),
    seg_version TEXT NOT NULL,
    CHECK (end_s > start_s)
);

CREATE INDEX idx_segments_video ON segments(video_id, start_s);

CREATE TABLE runs (
    run_id      TEXT PRIMARY KEY,
    stage       TEXT NOT NULL,
    method      TEXT,
    params_json TEXT NOT NULL DEFAULT '{}',
    model       TEXT,
    started_at  TIMESTAMP NOT NULL,
    finished_at TIMESTAMP,
    n_items     INTEGER NOT NULL DEFAULT 0,
    cost_usd    DECIMAL(10, 4) NOT NULL DEFAULT 0,
    status      TEXT NOT NULL CHECK (status IN ('running', 'ok', 'failed', 'blocked')),
    watermark   TEXT,
    error       TEXT
);

CREATE INDEX idx_runs_stage ON runs(stage, started_at);

CREATE TABLE llm_calls (
    call_hash      TEXT PRIMARY KEY,
    provider       TEXT NOT NULL,
    model          TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    input_tokens   INTEGER NOT NULL CHECK (input_tokens >= 0),
    output_tokens  INTEGER NOT NULL CHECK (output_tokens >= 0),
    cost_usd       DECIMAL(10, 6) NOT NULL CHECK (cost_usd >= 0),
    response_json  TEXT NOT NULL,
    created_at     TIMESTAMP NOT NULL
);

CREATE TABLE validation (
    run_id          TEXT NOT NULL REFERENCES runs(run_id),
    segment_id      TEXT NOT NULL REFERENCES segments(segment_id),
    validator_model TEXT NOT NULL,
    agreement       REAL CHECK (agreement >= 0 AND agreement <= 1),
    human_label     TEXT,
    PRIMARY KEY (run_id, segment_id)
);
