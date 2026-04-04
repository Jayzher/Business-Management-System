-- Table: accounts_role (5 rows)
-- Paste this into Neon SQL Editor

INSERT INTO "accounts_role" ("id", "created_at", "updated_at", "name", "description") VALUES
  (1, '2026-02-12 12:53:30.714921', '2026-02-12 12:53:30.714953', 'Admin', 'Admin role'),
  (2, '2026-02-12 12:53:30.724074', '2026-02-12 12:53:30.724093', 'Warehouse Manager', 'Warehouse Manager role'),
  (3, '2026-02-12 12:53:30.724543', '2026-02-12 12:53:30.724553', 'Encoder', 'Encoder role'),
  (4, '2026-02-12 12:53:30.725007', '2026-02-12 12:53:30.725018', 'Checker', 'Checker role'),
  (5, '2026-02-12 12:53:30.725463', '2026-02-12 12:53:30.725474', 'Viewer', 'Viewer role')
ON CONFLICT DO NOTHING;

SELECT setval(pg_get_serial_sequence('accounts_role', 'id'), COALESCE((SELECT MAX(id) FROM "accounts_role"), 1));
