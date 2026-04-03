-- Table: pricing_pricelist (12 rows)
-- Paste this into Neon SQL Editor

INSERT INTO "pricing_pricelist" ("id", "created_at", "updated_at", "is_active", "name", "currency", "is_default", "warehouse_id") VALUES
  (1, '2026-02-19 14:12:30.502032', '2026-02-25 15:00:32.624106', 0, 'Rectangular Tube 1/2x1 Powdercoat', 'PHP', 0, 2),
  (2, '2026-03-07 13:17:31.653896', '2026-03-07 16:13:13.028803', 1, '798 Series PCW Set', 'PHP', 0, 2),
  (3, '2026-03-07 16:09:23.283673', '2026-03-09 13:02:57.511841', 1, '798 Series Analok Set', 'PHP', 0, 2),
  (4, '2026-03-07 16:20:26.527485', '2026-03-07 16:29:51.731648', 0, 'Magic 7 PCW Set', 'PHP', 0, 2),
  (5, '2026-03-07 16:21:30.667153', '2026-03-07 16:31:43.776322', 1, 'Magic 7 PCW Set', 'PHP', 0, 2),
  (6, '2026-03-07 16:28:22.923039', '2026-03-19 03:37:23.419679', 1, 'Magic 7 Analok Set', 'PHP', 0, 2),
  (7, '2026-03-07 16:35:02.082292', '2026-03-09 15:18:47.268470', 1, 'Snap on PCW', 'PHP', 0, 2),
  (8, '2026-03-07 16:38:21.042558', '2026-03-30 02:50:09.595321', 1, 'Snap on Analok', 'PHP', 0, 2),
  (9, '2026-03-11 13:49:27.977448', '2026-03-11 16:40:40.991519', 1, 'Snap on PCW new price', 'PHP', 0, 2),
  (10, '2026-03-11 16:06:51.011791', '2026-03-19 04:00:38.907547', 0, 'Snap on HA new price', 'PHP', 0, NULL),
  (11, '2026-03-19 09:54:13.264367', '2026-03-26 02:25:59.942230', 0, 'Updated price dark gray 48x72', 'PHP', 0, 2),
  (12, '2026-03-26 03:04:06.692029', '2026-03-26 03:05:08.410021', 1, 'SD/MAGIC 7 w/ Screen', 'PHP', 0, 2)
ON CONFLICT DO NOTHING;

SELECT setval(pg_get_serial_sequence('pricing_pricelist', 'id'), COALESCE((SELECT MAX(id) FROM "pricing_pricelist"), 1));
