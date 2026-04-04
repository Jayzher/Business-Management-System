-- Table: catalog_productspec (3 rows)
-- Paste this into Neon SQL Editor

INSERT INTO "catalog_productspec" ("id", "created_at", "updated_at", "is_active", "model_name", "variant", "dimensions", "weight", "item_id") VALUES
  (1, '2026-02-12 12:53:30.770787', '2026-02-12 12:53:30.770797', 1, 'DT-100', '', '120x80x75cm', NULL, 7),
  (2, '2026-02-12 12:53:30.771835', '2026-02-12 12:53:30.771844', 1, 'CH-200', '', '45x45x90cm', NULL, 8),
  (3, '2026-02-12 12:53:30.772739', '2026-02-12 12:53:30.772748', 1, 'SW-120', '', '120x100cm', NULL, 9)
ON CONFLICT DO NOTHING;

SELECT setval(pg_get_serial_sequence('catalog_productspec', 'id'), COALESCE((SELECT MAX(id) FROM "catalog_productspec"), 1));
