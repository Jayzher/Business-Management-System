-- Table: pos_pospayment (3 rows)
-- Paste this into Neon SQL Editor

INSERT INTO "pos_pospayment" ("id", "created_at", "updated_at", "method", "amount", "reference_no", "paid_at", "sale_id") VALUES
  (4, '2026-03-12 08:19:19.480673', '2026-03-12 08:19:19.480690', 'CASH', 150, '', '2026-03-12 08:19:19.480720', 18),
  (5, '2026-03-17 07:48:41.624191', '2026-03-17 07:48:41.624208', 'CASH', 224, '', '2026-03-17 07:48:41.624238', 19),
  (6, '2026-03-17 07:49:35.986155', '2026-03-17 07:49:35.986176', 'CASH', 900, '', '2026-03-17 07:49:35.986230', 20)
ON CONFLICT DO NOTHING;

SELECT setval(pg_get_serial_sequence('pos_pospayment', 'id'), COALESCE((SELECT MAX(id) FROM "pos_pospayment"), 1));
