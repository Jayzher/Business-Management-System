-- Table: core_saleschannel (1 rows)
-- Paste this into Neon SQL Editor

INSERT INTO "core_saleschannel" ("id", "created_at", "updated_at", "is_active", "name", "code", "description") VALUES
  (1, '2026-02-19 11:39:06.230230', '2026-02-19 11:39:06.230246', 1, 'Physical Store', 'CUS-001', 'PROFIT GAIN HERE')
ON CONFLICT DO NOTHING;

SELECT setval(pg_get_serial_sequence('core_saleschannel', 'id'), COALESCE((SELECT MAX(id) FROM "core_saleschannel"), 1));
