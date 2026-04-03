-- Table: sales_salesreturn (1 rows)
-- Paste this into Neon SQL Editor

INSERT INTO "sales_salesreturn" ("id", "created_at", "updated_at", "is_active", "document_number", "status", "notes", "approved_at", "posted_at", "return_date", "reason", "approved_by_id", "created_by_id", "customer_id", "delivery_note_id", "posted_by_id", "sales_order_id", "warehouse_id") VALUES
  (1, '2026-03-27 15:17:36.921003', '2026-03-27 15:18:13.659013', 1, 'RET-SALES-001', 'POSTED', '', NULL, '2026-03-27 15:18:13.654694', '2026-03-27', 'Not fitted', NULL, 1, 7, 88, 1, 130, 2)
ON CONFLICT DO NOTHING;

SELECT setval(pg_get_serial_sequence('sales_salesreturn', 'id'), COALESCE((SELECT MAX(id) FROM "sales_salesreturn"), 1));
