-- Table: inventory_inventorytosupplytransferline (26 rows)
-- Paste this into Neon SQL Editor

INSERT INTO "inventory_inventorytosupplytransferline" ("id", "qty", "batch_number", "notes", "item_id", "location_id", "transfer_id", "unit_id", "supply_item_id") VALUES
  (2, 3, '', '', 2016, 12, 2, 1, NULL),
  (3, 7, '', '', 1942, 12, 2, 1, NULL),
  (4, 1, '', '', 1934, 12, 2, 1, NULL),
  (5, 1, '', '', 1931, 12, 2, 1, NULL),
  (6, 1, '', '', 2087, 12, 2, 1, NULL),
  (7, 1, '', '', 1933, 12, 2, 1, NULL),
  (8, 1, '', '', 1940, 12, 2, 1, NULL),
  (9, 1, '', '', 1943, 12, 2, 1, NULL),
  (10, 1, '', '', 2095, 12, 2, 1, NULL),
  (11, 1, '', '', 1931, 12, 2, 1, NULL),
  (12, 2, '', '', 2016, 12, 2, 1, NULL),
  (13, 3, '', '', 2078, 12, 2, 4, NULL),
  (14, 1, '', '', 2077, 12, 2, 4, NULL),
  (15, 2, '', '', 2096, 12, 3, 1, NULL),
  (16, 3, '', '', 2016, 12, 3, 1, NULL),
  (17, 1, '', '', 1928, 12, 3, 1, NULL),
  (18, 1, '', '', 2180, 12, 3, 1, NULL),
  (19, 4, '', '', 2165, 12, 3, 1, NULL),
  (20, 1, '', '', 2142, 12, 4, 1, NULL),
  (21, 2, '', '', 2048, 12, 4, 1, NULL),
  (23, 1, '', '', 2169, 12, 4, 15, NULL),
  (24, 1, '', '', 2105, 12, 4, 1, NULL),
  (25, 1, '', '', 2088, 12, 4, 1, NULL),
  (26, 1, '', '', 2105, 12, 4, 1, NULL),
  (27, 1, '', '', 2021, 12, 5, 1, NULL),
  (28, 1, '', '', 2088, 12, 5, 1, NULL)
ON CONFLICT DO NOTHING;

SELECT setval(pg_get_serial_sequence('inventory_inventorytosupplytransferline', 'id'), COALESCE((SELECT MAX(id) FROM "inventory_inventorytosupplytransferline"), 1));
