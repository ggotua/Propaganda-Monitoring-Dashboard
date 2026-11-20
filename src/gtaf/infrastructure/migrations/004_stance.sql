-- 004: stance labels (SPEC-013).
--
-- Separate from `llm_calls` because the call cache answers "what did the model reply to this exact
-- prompt", while this table answers "which label is currently attached to this segment and target".
-- They differ when a prompt version changes: the cache keeps the old reply, the label is superseded.

CREATE TABLE IF NOT EXISTS stance (
    segment_id     TEXT NOT NULL REFERENCES segments(segment_id),
    target         TEXT NOT NULL,
    label          TEXT NOT NULL CHECK (label IN ('supportive', 'critical', 'neutral', 'unclear')),
    confidence     REAL CHECK (confidence >= 0 AND confidence <= 1),
    model          TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    run_id         TEXT REFERENCES runs(run_id),
    rationale      TEXT,
    created_at     TIMESTAMP NOT NULL,
    PRIMARY KEY (segment_id, target, model, prompt_version)
);

CREATE INDEX IF NOT EXISTS idx_stance_target ON stance(target, label);

UPDATE schema_meta SET value = '4' WHERE key = 'schema_version';
