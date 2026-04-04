-- Table: services_customerservice (12 rows)
-- Paste this into Neon SQL Editor

INSERT INTO "services_customerservice" ("id", "service_number", "service_name", "customer_name", "service_date", "completion_date", "address", "notes", "status", "payment_status", "amount", "posted_at", "created_at", "updated_at", "created_by_id", "invoice_id", "posted_by_id", "warehouse_id", "discount_type", "discount_value", "quotation", "partial_payment_amount") VALUES
  (1, 'SVC-0001', 'Fixed Window Glass', 'Ton-Ton Macapas', '2026-03-06', '2026-03-06', 'Surallah', '', 'COMPLETED', 'UNPAID', NULL, '2026-03-26 17:03:28.708370', '2026-03-25 15:23:52.728521', '2026-03-27 01:43:04.698457', 1, 126, 1, 2, 'FIXED', 0, 8400, 0),
  (2, 'SVC-003', 'Screen Door  white', 'Unknown', '2026-03-19', '2026-03-23', 'Bugkos, Surallah', '', 'COMPLETED', 'UNPAID', NULL, '2026-03-27 02:00:10.539194', '2026-03-26 03:41:59.414146', '2026-03-27 02:00:10.567750', 1, 128, 1, 2, 'FIXED', 0, 7820, 0),
  (3, 'SVC-004', 'Sliding Window w/ Screen', 'Louis Belen', '2026-03-20', '2026-03-24', 'zone 6, Surallah', '', 'COMPLETED', 'UNPAID', NULL, '2026-03-27 01:57:21.241427', '2026-03-26 08:53:46.401418', '2026-03-27 01:57:21.272477', 1, 127, 1, 2, 'FIXED', 0, 29600, 0),
  (4, 'SVC-002', 'Sta Ana Window Glass Installed', 'Isko', '2026-03-12', '2026-03-13', '', '', 'COMPLETED', 'UNPAID', NULL, '2026-03-27 02:09:11.779256', '2026-03-27 02:07:42.901658', '2026-03-27 02:09:11.797199', 1, 129, 1, 2, 'FIXED', 0, 6600, 0),
  (5, 'Rpr-001', 'Tricycle side mirror', 'Walk-in Costumer', '2026-02-24', '2026-02-24', 'Surallah', '', 'COMPLETED', 'PAID', NULL, '2026-03-27 02:33:04.620556', '2026-03-27 02:31:18.097227', '2026-03-27 02:33:04.627061', 1, 130, 1, 2, 'FIXED', 0, 250, 250),
  (6, 'Rpr-002', 'Display Cabinet repair', 'Walk-in Customer', '2026-02-27', '2026-03-03', 'Lamsugod', '', 'COMPLETED', 'PAID', NULL, '2026-03-27 02:35:17.868905', '2026-03-27 02:34:26.830050', '2026-03-27 02:35:17.876290', 1, 131, 1, 2, 'FIXED', 0, 475, 475),
  (7, 'Rpr-003', 'Truck Driver Seat window Shield Glass Fixed', 'Walk-in Costumer', '2026-03-12', '2026-03-12', 'Surallah', '', 'COMPLETED', 'PAID', NULL, '2026-03-27 02:38:50.151223', '2026-03-27 02:38:25.556525', '2026-03-27 02:38:50.157058', 1, 132, 1, 2, 'FIXED', 0, 250, 250),
  (8, 'Rpr-004', 'Tricycle Wind Shield Glass Front Installed', 'Walk-in Costumer', '2026-03-17', '2026-03-17', 'Surallah', '', 'COMPLETED', 'PAID', NULL, '2026-03-27 02:42:15.442479', '2026-03-27 02:41:40.181325', '2026-03-27 02:51:43.523384', 1, 133, 1, 2, 'FIXED', 0, 450, 450),
  (9, 'Rpr-005', 'Tricycle Wind Shield Glass Bottom Front Installed', 'Panoy', '2026-03-17', '2026-03-17', 'Dajay, Surallah', '', 'COMPLETED', 'PAID', NULL, '2026-03-27 02:53:41.069907', '2026-03-27 02:45:09.717005', '2026-03-27 02:53:41.079802', 1, 134, 1, 2, 'FIXED', 0, 200, 200),
  (10, 'Rpr-0005', 'Tricycle Front Mirror', 'Walk-in Costumer', '2026-03-20', '2026-03-20', 'Surallah', '', 'COMPLETED', 'PAID', NULL, '2026-03-27 02:55:16.607659', '2026-03-27 02:54:57.780900', '2026-03-27 02:55:16.613374', 1, 135, 1, 2, 'FIXED', 0, 100, 100),
  (11, 'Rpr-006', 'Tricycle Wind Shield Glass Front Repair', 'Walk-in Costumer', '2026-03-23', '2026-03-23', 'Centrala, Surallah', '', 'COMPLETED', 'PAID', NULL, '2026-03-27 02:56:57.927590', '2026-03-27 02:56:24.016275', '2026-03-27 02:56:57.933144', 1, 136, 1, 2, 'FIXED', 0, 200, 200),
  (12, 'SVC-005', 'Kitchen Cabinet', 'Mendoza', '2026-03-25', NULL, 'Koronadal City', '', 'IN_PROGRESS', 'PARTIAL', NULL, NULL, '2026-03-27 03:09:56.133853', '2026-04-01 17:26:39.150262', 1, NULL, NULL, 2, 'FIXED', 0, 75000, 30000)
ON CONFLICT DO NOTHING;

SELECT setval(pg_get_serial_sequence('services_customerservice', 'id'), COALESCE((SELECT MAX(id) FROM "services_customerservice"), 1));
