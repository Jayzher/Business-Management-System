-- Table: sales_salesreturnline (1 rows)
-- Paste this into Neon SQL Editor

INSERT INTO "sales_salesreturnline" ("id", "qty", "reason", "notes", "item_id", "location_id", "sales_return_id", "unit_id") VALUES
  (1, 2, 'not fitted or not appropriate to a material', 'no damage(refunded)', 2157, 12, 1, 1)
ON CONFLICT DO NOTHING;

SELECT setval(pg_get_serial_sequence('sales_salesreturnline', 'id'), COALESCE((SELECT MAX(id) FROM "sales_salesreturnline"), 1));
