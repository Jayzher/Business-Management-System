-- Table: pricing_customerpricecatalog (9 rows)
-- Paste this into Neon SQL Editor

INSERT INTO "pricing_customerpricecatalog" ("id", "created_at", "updated_at", "is_active", "name", "notes", "customer_id", "end_date", "start_date") VALUES
  (1, '2026-03-07 15:35:53.042533', '2026-03-23 12:59:14.859918', 1, 'Jezreel Discounted Prices', '', 3, '2026-12-31', '2026-03-12'),
  (2, '2026-03-07 16:59:28.613830', '2026-03-30 02:50:53.993435', 1, 'Sherwin Discounted Prices', 'for solid Installer costumer', 4, '2026-12-31', '2026-03-13'),
  (3, '2026-03-17 04:03:15.556386', '2026-03-17 07:20:37.109946', 1, 'Doy-Doy glass privilege discounts', '', 15, '2026-12-31', '2026-03-17'),
  (4, '2026-03-17 05:57:19.153720', '2026-03-30 04:12:00.449782', 1, 'Balong Installer Discounts', '', 22, '2026-12-31', '2026-03-16'),
  (5, '2026-03-17 06:21:47.180986', '2026-03-17 06:21:47.181005', 1, 'Gentle Installer Discount Price', '', 6, '2026-12-31', '2026-03-16'),
  (6, '2026-03-17 07:26:44.384552', '2026-03-30 05:55:35.676004', 1, 'Ren-Ren Installer Discount Prices', '', 9, '2026-12-31', '2026-03-17'),
  (7, '2026-03-17 16:02:26.829104', '2026-03-17 16:05:18.172223', 1, 'Ranz Installer Discounted price', '', 12, '2026-12-31', '2026-03-17'),
  (8, '2026-03-19 01:57:19.983716', '2026-03-19 01:57:19.983733', 1, 'Arjan Installer Discounted price', '', 2, '2026-12-31', '2026-03-19'),
  (9, '2026-04-01 14:29:41.541930', '2026-04-01 14:37:55.950136', 1, 'Installer Lopez Discounted Price', '', 34, '2026-12-31', '2026-02-01')
ON CONFLICT DO NOTHING;

SELECT setval(pg_get_serial_sequence('pricing_customerpricecatalog', 'id'), COALESCE((SELECT MAX(id) FROM "pricing_customerpricecatalog"), 1));
