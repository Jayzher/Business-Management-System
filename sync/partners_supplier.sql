-- Table: partners_supplier (11 rows)
-- Paste this into Neon SQL Editor

INSERT INTO "partners_supplier" ("id", "created_at", "updated_at", "is_active", "code", "name", "contact_person", "email", "phone", "address", "city", "notes") VALUES
  (1, '2026-02-12 12:53:30.757435', '2026-02-17 09:59:34.166742', 1, 'SUP-001', 'LKS Aluminum and Glass corp.', '', 'lks_aluminumglass@yahoo.com', '+1 918-948-6292', 'door 10 & 11 purok virgo, brgy lasang, davao city', 'Davao City, Philippines, 8000', ''),
  (2, '2026-02-12 12:53:30.758232', '2026-02-17 10:04:42.278767', 1, 'SUP-002', 'CHY 1983 Aluminum and Glass Corp', '', 'chy1983aluminum@gmail.com', '09493320789', 'Mahayahay, Pangi', 'Davao City 8311', ''),
  (3, '2026-02-12 12:53:30.758797', '2026-02-17 10:08:25.908156', 1, 'SUP-003', 'AC GLASS', '', 'acglassvillasis@gmail.com', '0917 159 2139', 'Pangasinan, Philippines', 'Pangasinan', ''),
  (4, '2026-03-04 18:32:44.199968', '2026-03-07 16:54:32.051327', 1, 'SUP-004', 'YMS', '', '', '', '', 'Gensan', ''),
  (5, '2026-03-04 18:36:00.601113', '2026-03-04 18:36:42.641341', 1, 'SUP-005', 'HALIFAX GLASS &  Aluminum Supply', '', 'glasshalifax@gmail.com', '0939 924 3876', 'Saavedra Bldg., Times Beach, Matina Aplaya, Philippines', 'Davao City', ''),
  (6, '2026-03-04 18:39:08.934117', '2026-03-15 11:00:53.955303', 1, 'SUP-006', 'Elegant Prime Line Aluminum and Glass Corp.', '', '', '', '', 'Gensan', ''),
  (7, '2026-03-04 18:40:02.230261', '2026-03-04 18:40:02.230274', 1, 'SUP-007', 'ASYA GLASS', '', '', '', '', 'Koronadal', ''),
  (8, '2026-03-05 18:03:58.610128', '2026-03-07 16:50:17.939820', 1, 'SUP-008', 'SHOPPEE', '', '', '', '', '', ''),
  (9, '2026-03-07 16:53:34.500032', '2026-03-07 16:54:10.374843', 1, 'SUP-009', 'Tresscai Aluminum Glass Supply', '', 'Tresscaialuminumandglass@gmail.com', '09553279238', 'Brgy. Tambler', 'General Santos City', ''),
  (10, '2026-03-18 03:03:54.254534', '2026-03-18 03:03:54.254550', 1, 'Sup-10', 'Jacksa', '', '', '', 'Surallah', '', ''),
  (11, '2026-03-26 06:18:23.267196', '2026-03-26 06:18:23.267217', 1, 'SUP-010', 'Metrix Bolts Center', 'Russel D. Quezon', 'metrixboltscenter.koronadal@gmail.com', '09853925537', 'Door 3&4, Wilfredo Dizon Building, Gensan Drive, Brgy. Zone 3, Koronadal City South Cotabato 9506', 'Koronadal City', '')
ON CONFLICT DO NOTHING;

SELECT setval(pg_get_serial_sequence('partners_supplier', 'id'), COALESCE((SELECT MAX(id) FROM "partners_supplier"), 1));
