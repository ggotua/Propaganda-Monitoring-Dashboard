-- 006: a validation sample is not a pipeline run (SPEC-016).
--
-- `validation.run_id` was NOT NULL, written when the only imagined producer was a pipeline stage. A
-- cross-vendor check of stored labels is an ad-hoc audit of existing results, so it has no run of its own;
-- forcing one would create empty run rows whose only content is "someone checked 50 labels".
--
-- The table is empty at this migration (measured before writing it), so a rebuild is cheap and needs no
-- data copy.

DROP TABLE IF EXISTS validation;

CREATE TABLE validation (
    run_id          TEXT REFERENCES runs(run_id),
    segment_id      TEXT NOT NULL REFERENCES segments(segment_id),
    validator_model TEXT NOT NULL,
    agreement       REAL CHECK (agreement >= 0 AND agreement <= 1),
    human_label     TEXT,
    PRIMARY KEY (segment_id, validator_model)
);

UPDATE schema_meta SET value = '6' WHERE key = 'schema_version';
