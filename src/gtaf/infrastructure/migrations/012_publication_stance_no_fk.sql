-- 012: drop the foreign key from publication_stance (SPEC-018).
--
-- Measured 2026-11-26: DuckDB refuses to UPDATE a row that another table references, and it implements
-- ON CONFLICT DO UPDATE as delete+insert. Both mean a re-ingested publication cannot refresh its title or
-- excerpt once it has stance labels, and re-ingesting is exactly what a nightly run does.
--
-- The reference is dropped rather than the feature. Integrity is kept by the ingest path: a label is only
-- ever written for a publication id read from the publications table in the same process.

CREATE TABLE publication_stance_rebuilt (
    publication_id TEXT NOT NULL,
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

INSERT INTO publication_stance_rebuilt
SELECT publication_id, target, label, confidence, model, prompt_version, quote, quote_verified,
       rationale, created_at
FROM publication_stance;

DROP TABLE publication_stance;

ALTER TABLE publication_stance_rebuilt RENAME TO publication_stance;

CREATE INDEX IF NOT EXISTS idx_publication_stance_target
    ON publication_stance(target, label);

UPDATE schema_meta SET value = '12' WHERE key = 'schema_version';
