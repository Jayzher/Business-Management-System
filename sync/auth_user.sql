-- Table: auth_user (3 rows)
-- Paste this into Neon SQL Editor

INSERT INTO "auth_user" ("id", "password", "last_login", "is_superuser", "username", "first_name", "last_name", "email", "is_staff", "is_active", "date_joined", "phone", "avatar") VALUES
  (1, 'pbkdf2_sha256$1200000$oUL2MQ5J5m9OSP3GACnnE4$qjS7Y3yMnmCL/p30UfF/bJJj55/LF1CEoXDK8YMJ2MY=', '2026-03-30 15:30:15.719270', 1, 'admin', '', '', 'admin@wis.local', 1, 1, '2026-02-12 12:53:20.257138', '', ''),
  (3, 'pbkdf2_sha256$1000000$pWZPEs1X5xAXdydMqWzzEc$9rerJjzjlOp9D129x4sBSASWgup2t7JXBsKkEX6bPIU=', '2026-03-18 11:05:20.973292', 1, 'admin_tst2', '', '', 't@t.com', 1, 1, '2026-03-18 11:05:20.181638', '', ''),
  (4, 'pbkdf2_sha256$1200000$lqROpJbwMxZLnEQ6UiGHvc$+xBLkjNf7jExIzrfFkAAt7NZlsIc5AxHBO1wPyIXkeQ=', '2026-03-30 12:38:43.243926', 0, 'bigboss', '', '', '', 0, 1, '2026-03-30 12:36:09.223095', '', '')
ON CONFLICT DO NOTHING;

SELECT setval(pg_get_serial_sequence('auth_user', 'id'), COALESCE((SELECT MAX(id) FROM "auth_user"), 1));
