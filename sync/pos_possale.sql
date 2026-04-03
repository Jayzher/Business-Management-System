-- Table: pos_possale (4 rows)
-- Paste this into Neon SQL Editor

INSERT INTO "pos_possale" ("id", "created_at", "updated_at", "sale_no", "status", "subtotal", "discount_total", "tax_total", "grand_total", "posted_at", "notes", "created_by_id", "customer_id", "location_id", "posted_by_id", "register_id", "warehouse_id", "shift_id", "channel_id", "stock_deducted") VALUES
  (18, '2026-03-12 08:19:03.898457', '2026-03-12 08:19:19.660898', 'POS-000001', 'POSTED', 150, 0, 0, 150, '2026-03-12 08:19:19.656145', '', 1, NULL, 12, 1, 1, 2, 4, NULL, 1),
  (19, '2026-03-17 07:48:08.969568', '2026-03-17 07:48:41.819467', 'POS-000019', 'POSTED', 224, 0, 0, 224, '2026-03-17 07:48:41.815333', '', 1, NULL, 12, 1, 1, 2, 5, NULL, 1),
  (20, '2026-03-17 07:49:01.440671', '2026-03-17 07:49:36.206715', 'POS-000020', 'POSTED', 900, 0, 0, 900, '2026-03-17 07:49:36.192266', '', 1, NULL, 12, 1, 1, 2, 5, NULL, 1),
  (21, '2026-03-17 07:49:39.851492', '2026-03-17 07:49:39.851510', 'POS-000021', 'DRAFT', 0, 0, 0, 0, NULL, '', 1, NULL, 12, NULL, 1, 2, 5, NULL, 0)
ON CONFLICT DO NOTHING;

SELECT setval(pg_get_serial_sequence('pos_possale', 'id'), COALESCE((SELECT MAX(id) FROM "pos_possale"), 1));
