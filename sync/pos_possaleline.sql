-- Table: pos_possaleline (3 rows)
-- Paste this into Neon SQL Editor

INSERT INTO "pos_possaleline" ("id", "qty", "unit_price", "discount_amount", "tax_rate", "line_total", "batch_number", "serial_number", "qr_uid_used", "item_id", "location_id", "sale_id", "unit_id") VALUES
  (12, 1, 150, 0, 0, 150, '', '', NULL, 2018, 12, 18, 1),
  (13, 8, 28, 0, 0, 224, '', '', NULL, 2134, 12, 19, 13),
  (14, 6, 150, 0, 0, 900, '', '', NULL, 2016, 12, 20, 1)
ON CONFLICT DO NOTHING;

SELECT setval(pg_get_serial_sequence('pos_possaleline', 'id'), COALESCE((SELECT MAX(id) FROM "pos_possaleline"), 1));
