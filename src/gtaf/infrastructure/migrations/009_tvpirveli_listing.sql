-- 009: TV Pirveli discovers from its politics section, not from the sitemap (SPEC-018).
--
-- Measured 2026-11-26: the section page `/ka/siaxleebi/politika` carries 27 current article links, while the
-- sitemap carries 21,619 URLs in no useful recency order. A daily run wants today's politics, not an arbitrary
-- slice of the archive; the sitemap stays available for a deliberate backfill.

UPDATE sources
SET kind = 'listing',
    listing_url = 'https://tvpirveli.ge/ka/siaxleebi/politika'
WHERE source_id = 'tvpirveli';

UPDATE schema_meta SET value = '9' WHERE key = 'schema_version';
