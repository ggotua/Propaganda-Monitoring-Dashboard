-- 015: per-source link pattern for listing discovery (SPEC-018).
--
-- Measured 2026-11-28: Rustavi 2's listing links live at `/ka/news/372678`, so the shared pattern used for the
-- other two outlets matched nothing and the ingest stored zero publications. A per-source pattern is the honest
-- place for this: the URL shape is a property of the site, not of the pipeline.

ALTER TABLE sources ADD COLUMN IF NOT EXISTS link_pattern TEXT;

UPDATE sources SET link_pattern = '/ge/' WHERE source_id = 'imedi';
UPDATE sources SET link_pattern = '/ka/siaxleebi/' WHERE source_id = 'tvpirveli';
UPDATE sources SET link_pattern = '/News/' WHERE source_id = 'formula';
UPDATE sources SET link_pattern = '/ka/news/\d' WHERE source_id = 'rustavi2';

UPDATE schema_meta SET value = '15' WHERE key = 'schema_version';
