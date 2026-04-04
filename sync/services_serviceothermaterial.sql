-- Table: services_serviceothermaterial (8 rows)
-- Paste this into Neon SQL Editor

INSERT INTO "services_serviceothermaterial" ("id", "item_name", "qty", "unit_price", "vendor", "notes", "service_id") VALUES
  (1, 'door knob', 2, 170, '', '', 2),
  (2, '3x3 hinges', 2, 65, '', '', 2),
  (3, 'hand riveter', 1, 189, '', '', 3),
  (4, 'cutter knife', 1, 53, '', '', 3),
  (5, 'side scraper', 1, 30, '', '', 3),
  (6, 'cordless drill', 1, 1150, '', '', 3),
  (7, 'Metal Screw 8x2', 50, 2, '', '', 4),
  (8, 'Yestar Drawer Guide Slide', 6, 155, 'Maunlad', '', 12)
ON CONFLICT DO NOTHING;

SELECT setval(pg_get_serial_sequence('services_serviceothermaterial', 'id'), COALESCE((SELECT MAX(id) FROM "services_serviceothermaterial"), 1));
