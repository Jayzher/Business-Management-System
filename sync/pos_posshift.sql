-- Table: pos_posshift (2 rows)
-- Paste this into Neon SQL Editor

INSERT INTO "pos_posshift" ("id", "created_at", "updated_at", "opened_at", "opening_cash", "closed_at", "closing_cash_declared", "status", "cash_sales_total", "noncash_sales_total", "refund_total", "cash_in_out_total", "closed_by_id", "opened_by_id", "register_id") VALUES
  (4, '2026-03-12 08:18:56.043573', '2026-03-16 11:47:05.027912', '2026-03-12 08:18:56', 500, '2026-03-12 11:47:01', 650, 'CLOSED', 150, 0, 0, 0, 1, 1, 1),
  (5, '2026-03-17 07:48:03.911773', '2026-03-17 16:12:18.367498', '2026-03-17 07:48:03.911507', 500, '2026-03-17 16:12:18.365003', 1624, 'CLOSED', 1124, 0, 0, 0, 1, 1, 1)
ON CONFLICT DO NOTHING;

SELECT setval(pg_get_serial_sequence('pos_posshift', 'id'), COALESCE((SELECT MAX(id) FROM "pos_posshift"), 1));
