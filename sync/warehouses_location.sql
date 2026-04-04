-- Table: warehouses_location (12 rows)
-- Paste this into Neon SQL Editor

INSERT INTO "warehouses_location" ("id", "created_at", "updated_at", "is_active", "code", "name", "location_type", "is_pickable", "parent_id", "warehouse_id") VALUES
  (1, '2026-02-12 12:53:30.750651', '2026-02-17 10:12:58.708140', 0, 'ZONE-A', 'Zone A - Raw Materials', 'ZONE', 0, NULL, 1),
  (2, '2026-02-12 12:53:30.751478', '2026-02-17 10:13:00.794737', 0, 'ZONE-B', 'Zone B - Finished Products', 'ZONE', 0, NULL, 1),
  (3, '2026-02-12 12:53:30.752107', '2026-02-17 10:12:37.691148', 0, 'A-R1-B1', 'Rack 1 Bin 1', 'BIN', 1, 1, 1),
  (4, '2026-02-12 12:53:30.752706', '2026-02-17 10:12:40.547285', 0, 'A-R1-B2', 'Rack 1 Bin 2', 'BIN', 1, 1, 1),
  (5, '2026-02-12 12:53:30.753296', '2026-02-17 10:12:42.810350', 0, 'A-R1-B3', 'Rack 1 Bin 3', 'BIN', 1, 1, 1),
  (6, '2026-02-12 12:53:30.753886', '2026-02-17 10:12:45.634053', 0, 'A-R1-B4', 'Rack 1 Bin 4', 'BIN', 1, 1, 1),
  (7, '2026-02-12 12:53:30.754565', '2026-02-17 10:12:48.364139', 0, 'A-R1-B5', 'Rack 1 Bin 5', 'BIN', 1, 1, 1),
  (8, '2026-02-12 12:53:30.755207', '2026-02-17 10:12:50.843301', 0, 'B-R1-B1', 'Rack 1 Bin 1', 'BIN', 1, 2, 1),
  (9, '2026-02-12 12:53:30.755791', '2026-02-17 10:12:53.235218', 0, 'B-R1-B2', 'Rack 1 Bin 2', 'BIN', 1, 2, 1),
  (10, '2026-02-12 12:53:30.756368', '2026-02-17 10:12:56.242745', 0, 'B-R1-B3', 'Rack 1 Bin 3', 'BIN', 1, 2, 1),
  (11, '2026-02-17 15:37:59.001545', '2026-03-04 18:41:27.537828', 0, 'GP-C', 'Surallah', 'BIN', 1, NULL, 1),
  (12, '2026-02-19 11:25:01.446471', '2026-03-04 18:42:25.749669', 1, 'MAIN', 'Jas-Maiah Physical Store', 'ZONE', 1, NULL, 2)
ON CONFLICT DO NOTHING;

SELECT setval(pg_get_serial_sequence('warehouses_location', 'id'), COALESCE((SELECT MAX(id) FROM "warehouses_location"), 1));
