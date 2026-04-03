-- Table: pricing_discountrule (2 rows)
-- Paste this into Neon SQL Editor

INSERT INTO "pricing_discountrule" ("id", "created_at", "updated_at", "is_active", "name", "discount_type", "value", "scope") VALUES
  (1, '2026-02-19 15:06:25.599226', '2026-03-07 16:02:36.935373', 0, '798 Series PCW set', 'FIXED', 3200, 'ORDER'),
  (2, '2026-02-19 15:07:11.650801', '2026-03-07 13:06:28.216738', 0, 'Jezreel Juaniza', 'PERCENT', 2, 'ITEM')
ON CONFLICT DO NOTHING;

SELECT setval(pg_get_serial_sequence('pricing_discountrule', 'id'), COALESCE((SELECT MAX(id) FROM "pricing_discountrule"), 1));
