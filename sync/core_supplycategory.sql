-- Table: core_supplycategory (3 rows)
-- Paste this into Neon SQL Editor

INSERT INTO "core_supplycategory" ("id", "created_at", "updated_at", "is_active", "name", "code") VALUES
  (1, '2026-02-19 11:57:16.258189', '2026-02-19 12:04:28.506233', 1, 'Aluminum Rectangular', 'ALU- Rec'),
  (2, '2026-03-23 13:36:01.234390', '2026-03-23 13:36:01.234407', 1, 'Accessories', 'SVC-ACCE-3X3HINGES'),
  (3, '2026-03-23 13:36:54.959992', '2026-03-23 13:36:54.960008', 1, 'Doorknob', 'SVC-ACCE-Doorknob')
ON CONFLICT DO NOTHING;

SELECT setval(pg_get_serial_sequence('core_supplycategory', 'id'), COALESCE((SELECT MAX(id) FROM "core_supplycategory"), 1));
