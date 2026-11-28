-- 014: third outlet, with its leaning explicitly unassigned (SPEC-018).
--
-- Rustavi 2 is added for volume and for supportive coverage. Its editorial leaning is not something this code
-- may invent: the schema's three values are all claims, and a placeholder claim would contaminate every
-- comparison that groups by leaning. `leaning_assigned` lets the outlet take part in corpus and stance counts
-- while being excluded from any claim that depends on knowing which side it is on.

ALTER TABLE sources ADD COLUMN IF NOT EXISTS leaning_assigned BOOLEAN;
UPDATE sources SET leaning_assigned = TRUE WHERE leaning_assigned IS NULL;

INSERT INTO sources (source_id, name_en, leaning, base_url, access_mode, kind, listing_url, leaning_note, leaning_assigned)
VALUES (
    'rustavi2',
    'Rustavi 2',
    'independent',
    'https://rustavi2.ge',
    'full',
    'listing',
    'https://rustavi2.ge/ka/news',
    'Third outlet added 2026-11-28 for volume and supportive coverage. Leaning NOT assigned: the value is a '
    'placeholder and must not be read as editorial judgement. Exclude from leaning comparisons until the '
    'project owner records one.',
    FALSE
);

UPDATE schema_meta SET value = '14' WHERE key = 'schema_version';
