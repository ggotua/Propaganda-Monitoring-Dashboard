-- 002_topics.sql — topic modelling output (SPEC-007).
--
-- Additive only: no existing table is altered, so a v1 database migrates without rewriting data.
-- The version marker is updated last, so a failure mid-migration leaves the database at v1 and the
-- migration can be re-run.

CREATE TABLE topics (
    run_id     TEXT NOT NULL REFERENCES runs(run_id),
    topic_id   INTEGER NOT NULL,
    label_ka   TEXT,
    label_en   TEXT,
    keywords   TEXT[] NOT NULL DEFAULT [],
    n_segments INTEGER NOT NULL CHECK (n_segments >= 0),
    PRIMARY KEY (run_id, topic_id)
);

CREATE TABLE res_topics (
    segment_id     TEXT PRIMARY KEY REFERENCES segments(segment_id),
    run_id         TEXT NOT NULL REFERENCES runs(run_id),
    topic_id       INTEGER NOT NULL,
    probability    REAL CHECK (probability >= 0 AND probability <= 1),
    method_version TEXT NOT NULL
);

CREATE INDEX idx_res_topics_topic ON res_topics(run_id, topic_id);

UPDATE schema_meta SET value = '2' WHERE key = 'schema_version';
