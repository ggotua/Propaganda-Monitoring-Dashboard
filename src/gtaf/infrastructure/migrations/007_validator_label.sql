-- 007: keep the validator's label, so agreement can be recomputed over everything checked so far.
--
-- The table stored only a 0/1 agreement flag. That is enough to count, and not enough to compute kappa or
-- per-class rates, which need both labellers' labels. Storing the validator's verdict makes a multi-day
-- accumulation possible: each day adds items, and the statistic is recomputed from the whole set.

ALTER TABLE validation ADD COLUMN IF NOT EXISTS validator_label TEXT;

UPDATE schema_meta SET value = '7' WHERE key = 'schema_version';
