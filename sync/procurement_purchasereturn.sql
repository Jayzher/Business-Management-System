-- Table: procurement_purchasereturn (2 rows)
-- Paste this into Neon SQL Editor

INSERT INTO "procurement_purchasereturn" ("id", "created_at", "updated_at", "is_active", "document_number", "status", "notes", "approved_at", "posted_at", "return_date", "reason", "approved_by_id", "created_by_id", "goods_receipt_id", "posted_by_id", "supplier_id", "warehouse_id") VALUES
  (1, '2026-03-27 14:56:16.150504', '2026-03-27 14:57:47.773673', 1, 'RET-3/27/26', 'POSTED', '', NULL, '2026-03-27 14:57:47.769303', '2026-03-27', 'DAMAGE', NULL, 1, 114, 1, 7, 2),
  (2, '2026-03-27 14:57:24.487864', '2026-03-27 14:57:32.877400', 1, 'RET-3/27/26-002', 'POSTED', '', NULL, '2026-03-27 14:57:32.872236', '2026-03-27', 'Damage', NULL, 1, 114, 1, 7, 2)
ON CONFLICT DO NOTHING;

SELECT setval(pg_get_serial_sequence('procurement_purchasereturn', 'id'), COALESCE((SELECT MAX(id) FROM "procurement_purchasereturn"), 1));
