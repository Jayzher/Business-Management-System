-- Table: catalog_materialspec (4 rows)
-- Paste this into Neon SQL Editor

INSERT INTO "catalog_materialspec" ("id", "created_at", "updated_at", "is_active", "thickness", "length", "width", "color", "alloy", "grade", "item_id") VALUES
  (1, '2026-02-12 12:53:30.765798', '2026-02-12 12:53:30.765809', 1, 1.2, 6, NULL, '', '6063-T5', '', 1),
  (2, '2026-02-12 12:53:30.766913', '2026-02-12 12:53:30.766923', 1, 1.5, 6, NULL, '', '6061-T6', '', 2),
  (3, '2026-02-12 12:53:30.767786', '2026-02-12 12:53:30.767796', 1, 6, 2.44, 1.22, '', '', '', 3),
  (4, '2026-02-12 12:53:30.768637', '2026-02-12 12:53:30.768647', 1, 8, 2.44, 1.22, '', '', '', 4)
ON CONFLICT DO NOTHING;

SELECT setval(pg_get_serial_sequence('catalog_materialspec', 'id'), COALESCE((SELECT MAX(id) FROM "catalog_materialspec"), 1));
