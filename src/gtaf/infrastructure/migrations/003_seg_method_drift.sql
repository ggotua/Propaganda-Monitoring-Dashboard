-- 003: allow drift and pause segmentation (SPEC-006, D-027).
--
-- Why a table rebuild: DuckDB 2.0 has no ALTER TABLE ... DROP CONSTRAINT ("No support for that ALTER
-- TABLE option yet", measured on a copy before touching the real database). The seg_method CHECK was
-- written when only three methods existed, and a new method cannot be inserted past it.
--
-- The child tables that reference segments (res_topics, validation) must be dropped first and recreated
-- after, because a referenced table cannot be renamed or dropped while a foreign key points at it. Both
-- hold derived results only: topics and validations are recomputed from segments, so losing them here
-- costs a re-run, not data.

DROP TABLE IF EXISTS validation;
DROP TABLE IF EXISTS res_topics;

-- The index must go before the rename: measured on a copy, `ALTER TABLE segments RENAME` fails with
-- "Cannot alter entry segments because there are entries that depend on it" while idx_segments_video
-- exists, and succeeds once it is dropped. The index is recreated at the end.
DROP INDEX IF EXISTS idx_segments_video;

ALTER TABLE segments RENAME TO segments_old;

CREATE TABLE segments (
    segment_id  TEXT PRIMARY KEY,
    video_id    TEXT NOT NULL REFERENCES videos(video_id),
    start_s     REAL NOT NULL CHECK (start_s >= 0),
    end_s       REAL NOT NULL,
    text        TEXT NOT NULL,
    title_ka    TEXT,
    title_en    TEXT,
    seg_method  TEXT NOT NULL CHECK (seg_method IN ('llm', 'texttiling', 'fixed', 'drift', 'pause')),
    seg_version TEXT NOT NULL,
    CHECK (end_s > start_s)
);

INSERT INTO segments (
    segment_id, video_id, start_s, end_s, text, title_ka, title_en, seg_method, seg_version
)
SELECT segment_id, video_id, start_s, end_s, text, title_ka, title_en, seg_method, seg_version
FROM segments_old;

DROP TABLE segments_old;

CREATE INDEX idx_segments_video ON segments(video_id, start_s);

CREATE TABLE res_topics (
    segment_id     TEXT PRIMARY KEY REFERENCES segments(segment_id),
    run_id         TEXT NOT NULL REFERENCES runs(run_id),
    topic_id       INTEGER NOT NULL,
    probability    REAL CHECK (probability >= 0 AND probability <= 1),
    method_version TEXT NOT NULL
);

CREATE INDEX idx_res_topics_topic ON res_topics(run_id, topic_id);

CREATE TABLE validation (
    run_id          TEXT NOT NULL REFERENCES runs(run_id),
    segment_id      TEXT NOT NULL REFERENCES segments(segment_id),
    validator_model TEXT NOT NULL,
    agreement       REAL CHECK (agreement >= 0 AND agreement <= 1),
    human_label     TEXT,
    PRIMARY KEY (run_id, segment_id)
);

UPDATE schema_meta SET value = '3' WHERE key = 'schema_version';
