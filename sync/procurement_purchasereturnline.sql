-- Table: procurement_purchasereturnline (2 rows)
-- Paste this into Neon SQL Editor

INSERT INTO "procurement_purchasereturnline" ("id", "qty", "reason", "notes", "item_id", "location_id", "purchase_return_id", "unit_id") VALUES
  (1, 1, 'DAMAGE', '', 2202, 12, 1, 4),
  (2, 1, 'DAMAGE', '', 2184, 12, 2, 4)
ON CONFLICT DO NOTHING;

SELECT setval(pg_get_serial_sequence('procurement_purchasereturnline', 'id'), COALESCE((SELECT MAX(id) FROM "procurement_purchasereturnline"), 1));
