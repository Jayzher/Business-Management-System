-- Table: inventory_inventorytosupplytransfer (4 rows)
-- Paste this into Neon SQL Editor

INSERT INTO "inventory_inventorytosupplytransfer" ("id", "created_at", "updated_at", "is_active", "document_number", "status", "notes", "approved_at", "posted_at", "transfer_date", "reason", "approved_by_id", "created_by_id", "posted_by_id", "warehouse_id") VALUES
  (2, '2026-03-23 14:43:26.839185', '2026-03-23 14:50:54.786026', 1, 'REFURBISHMENT-001', 'POSTED', '', NULL, '2026-03-23 14:50:54.733976', '2026-02-20', 'Making Display Showcase Cabinet', NULL, 1, 1, 2),
  (3, '2026-03-23 14:58:54.067658', '2026-03-23 15:05:09.733364', 1, 'REFURBISHMENT-002', 'POSTED', '', NULL, '2026-03-23 15:05:09.708432', '2026-02-28', 'Kitchen Cabinet shops', NULL, 1, 1, 2),
  (4, '2026-03-23 15:37:04.855894', '2026-03-24 06:40:24.073001', 1, 'REFURBISHMENT-003', 'POSTED', '', NULL, '2026-03-24 05:52:47', '2026-03-09', 'making a drawers for cashier table', NULL, 1, 1, 2),
  (5, '2026-03-24 06:34:47.042596', '2026-03-24 06:42:23.063834', 1, 'Tools-002', 'POSTED', '', NULL, '2026-03-24 06:42:23.051724', '2026-03-24', 'to use in shop', NULL, 1, 1, 2)
ON CONFLICT DO NOTHING;

SELECT setval(pg_get_serial_sequence('inventory_inventorytosupplytransfer', 'id'), COALESCE((SELECT MAX(id) FROM "inventory_inventorytosupplytransfer"), 1));
