-- Table: pos_posregister (1 rows)
-- Paste this into Neon SQL Editor

INSERT INTO "pos_posregister" ("id", "created_at", "updated_at", "is_active", "name", "receipt_footer", "default_location_id", "price_list_id", "warehouse_id") VALUES
  (1, '2026-02-19 14:07:31.628106', '2026-03-05 18:12:45.289007', 1, 'Jas-Maiah Physical Store', '', 12, NULL, 2)
ON CONFLICT DO NOTHING;

SELECT setval(pg_get_serial_sequence('pos_posregister', 'id'), COALESCE((SELECT MAX(id) FROM "pos_posregister"), 1));
