-- 013: stance rows record the text they were computed on (SPEC-018).
--
-- Measured 2026-11-28: after the extractor was fixed and article bodies changed, labels computed on the old
-- text stayed in place. One publication kept a `critical` label for Ivanishvili although the cleaned text does
-- not mention him at all — the mention came from a teaser that is no longer there.
--
-- The hash makes staleness detectable; the ingest path also deletes dependent labels when a body changes.

ALTER TABLE publication_stance ADD COLUMN IF NOT EXISTS text_hash TEXT;

UPDATE schema_meta SET value = '13' WHERE key = 'schema_version';
