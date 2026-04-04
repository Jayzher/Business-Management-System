-- Table: inventory_stocktransfer (1 rows)
-- Paste this into Neon SQL Editor

INSERT INTO "inventory_stocktransfer" ("id", "created_at", "updated_at", "is_active", "document_number", "status", "notes", "approved_at", "posted_at", "approved_by_id", "created_by_id", "from_warehouse_id", "posted_by_id", "to_warehouse_id") VALUES
  (1, '2026-02-19 12:14:29.913312', '2026-02-19 13:30:15.485492', 0, 'qwe', 'DRAFT', 'bought', NULL, NULL, NULL, 1, 2, NULL, 1)
ON CONFLICT DO NOTHING;

SELECT setval(pg_get_serial_sequence('inventory_stocktransfer', 'id'), COALESCE((SELECT MAX(id) FROM "inventory_stocktransfer"), 1));
