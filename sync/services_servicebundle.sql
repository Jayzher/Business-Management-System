-- Table: services_servicebundle (2 rows)
-- Paste this into Neon SQL Editor

INSERT INTO "services_servicebundle" ("id", "price_list_id", "service_id", "qty") VALUES
  (1, 8, 1, 3),
  (2, 9, 2, 2)
ON CONFLICT DO NOTHING;

SELECT setval(pg_get_serial_sequence('services_servicebundle', 'id'), COALESCE((SELECT MAX(id) FROM "services_servicebundle"), 1));
