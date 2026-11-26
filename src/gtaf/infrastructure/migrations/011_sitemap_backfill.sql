-- 011: sitemap discovery for backfill (SPEC-018).
--
-- One listing page holds ~25 articles, which is enough for a nightly delta and not enough for a comparison:
-- measured 2026-11-26, 46 publications produced 2 mentions of the prime minister. Both channels publish a
-- sitemap containing their whole archive, so a deliberate backfill can reach hundreds of articles without
-- crawling pagination guessing at query parameters.

ALTER TABLE sources ADD COLUMN IF NOT EXISTS sitemap_url TEXT;

UPDATE sources SET sitemap_url = 'https://imedi.ge/sitemap.xml' WHERE source_id = 'imedi';
UPDATE sources SET sitemap_url = 'https://tvpirveli.ge/_cmssitemap' WHERE source_id = 'tvpirveli';

UPDATE schema_meta SET value = '11' WHERE key = 'schema_version';
