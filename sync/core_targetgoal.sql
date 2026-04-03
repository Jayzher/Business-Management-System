-- Table: core_targetgoal (1 rows)
-- Paste this into Neon SQL Editor

INSERT INTO "core_targetgoal" ("id", "created_at", "updated_at", "title", "description", "category", "target_value", "current_value", "unit_label", "priority", "status", "due_date", "assigned_to_id", "created_by_id") VALUES
  (2, '2026-03-30 15:17:43.501475', '2026-03-30 15:17:43.501604', 'sales revenue for April', '', 'SALES', 500000, 0, 'PHP', 'HIGH', 'PENDING', '2026-04-30', NULL, 1)
ON CONFLICT DO NOTHING;

SELECT setval(pg_get_serial_sequence('core_targetgoal', 'id'), COALESCE((SELECT MAX(id) FROM "core_targetgoal"), 1));
