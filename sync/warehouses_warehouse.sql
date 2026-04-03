-- Table: warehouses_warehouse (2 rows)
-- Paste this into Neon SQL Editor

INSERT INTO "warehouses_warehouse" ("id", "created_at", "updated_at", "is_active", "code", "name", "address", "city", "phone", "allow_negative_stock", "manager_id") VALUES
  (1, '2026-02-12 12:53:30.749607', '2026-03-04 18:41:15.104403', 0, 'WH-MAIN', 'Juaniza Residence', 'Zone2-A', 'Surallah', '', 0, 1),
  (2, '2026-02-19 11:24:01.989621', '2026-03-04 18:43:11.767219', 1, 'SHOP-001', 'Jas-Maiah Physical Store', 'Tomas Pin-pin St.', 'Surallah', '09501945291', 1, 1)
ON CONFLICT DO NOTHING;

SELECT setval(pg_get_serial_sequence('warehouses_warehouse', 'id'), COALESCE((SELECT MAX(id) FROM "warehouses_warehouse"), 1));
