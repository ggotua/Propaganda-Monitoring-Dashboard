-- 005: stance labels must cite their evidence (SPEC-013 revision).
--
-- The first G-8 review found rationales that quoted words absent from the segment. A label whose stated
-- reason is invented cannot be reviewed, so the label now carries a verbatim quote and whether that quote
-- was actually found in the text.

ALTER TABLE stance ADD COLUMN IF NOT EXISTS quote TEXT;
ALTER TABLE stance ADD COLUMN IF NOT EXISTS quote_verified BOOLEAN;

UPDATE schema_meta SET value = '5' WHERE key = 'schema_version';
