-- 010: stance labels for web publications (SPEC-018).
--
-- A separate table from `stance`, on purpose: that one labels broadcast segments, this one labels article
-- text. Keeping them apart is what makes "never merge the corpora" (D-034) structural rather than a rule
-- somebody has to remember.

CREATE TABLE IF NOT EXISTS publication_stance (
    publication_id TEXT NOT NULL REFERENCES publications(publication_id),
    target         TEXT NOT NULL,
    label          TEXT NOT NULL CHECK (label IN ('supportive', 'critical', 'neutral', 'unclear')),
    confidence     REAL CHECK (confidence >= 0 AND confidence <= 1),
    model          TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    quote          TEXT,
    quote_verified BOOLEAN,
    rationale      TEXT,
    created_at     TIMESTAMP NOT NULL,
    PRIMARY KEY (publication_id, target, model, prompt_version)
);

CREATE INDEX IF NOT EXISTS idx_publication_stance_target
    ON publication_stance(target, label);

UPDATE schema_meta SET value = '10' WHERE key = 'schema_version';
