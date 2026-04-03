-- Table: core_businessprofile (1 rows)
-- Paste this into Neon SQL Editor

INSERT INTO "core_businessprofile" ("id", "name", "tagline", "owner_name", "email", "phone", "address", "city", "province", "zip_code", "country", "tin", "logo", "currency", "fiscal_year_start_month", "receipt_footer", "created_at", "updated_at") VALUES
  (1, 'Jas-Maiah Glass & Aluminum Supply', 'Where strength meets style', 'Raj & Joy', 'jas.maiah16@gmail.com', '09501945291', 'Tomas Pin-pin st.', 'Surallah', 'South Cotabato', '9512', 'Philippines', '', 'business/GLASS__ALUMINUM_SERVICES_3.png', 'PHP', 1, 'Thank you for visiting Jas-Maiah Glass & Aluminum Supply', '2026-02-14 19:07:17.121776', '2026-02-19 13:50:40.716538')
ON CONFLICT DO NOTHING;

SELECT setval(pg_get_serial_sequence('core_businessprofile', 'id'), COALESCE((SELECT MAX(id) FROM "core_businessprofile"), 1));
