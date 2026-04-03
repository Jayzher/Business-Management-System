-- Table: core_expensecategory (15 rows)
-- Paste this into Neon SQL Editor

INSERT INTO "core_expensecategory" ("id", "created_at", "updated_at", "is_active", "name", "code", "description", "is_cogs") VALUES
  (1, '2026-02-19 11:41:32.895761', '2026-02-19 11:42:52.254330', 1, 'Miscellaneous', 'EXP-001', 'Bank/Financial Fees, Office Costs, Subscriptions: One-time or minor , Minor Supplies business-related subscriptions.', 0),
  (2, '2026-02-19 11:44:26.343812', '2026-02-19 11:44:26.343828', 1, 'General and Administration', 'EXP-002', 'Salaries for non-sales personnel, office rent, utilities (electricity, internet), office supplies, insurance, legal fees, and administrative software subscriptions.', 0),
  (3, '2026-02-19 11:52:49.703285', '2026-03-12 13:01:18.706094', 1, 'Cost of Goods', 'EXP-003', 'direct costs to produce or buy the product you sell', 1),
  (4, '2026-03-12 12:58:58.779906', '2026-03-12 12:58:58.779923', 1, 'Office & Supplies', 'Exp-004', 'Items needed for daily operations.', 0),
  (5, '2026-03-12 13:00:16.041586', '2026-03-12 13:00:16.041604', 1, 'Marketing & Advertising', 'EXP-005', 'Money spent to promote your business.', 0),
  (6, '2026-03-12 13:01:09.898749', '2026-03-12 13:01:09.898771', 1, 'Rent & Utilities', 'Exp-006', 'Costs related to your business location.', 0),
  (7, '2026-03-12 13:02:07.885386', '2026-03-12 13:02:07.885415', 1, 'Software & Subscriptions', 'Exp-007', 'Digital tools used to run your business.', 0),
  (8, '2026-03-12 13:03:05.817056', '2026-03-12 13:03:05.817083', 1, 'Equipment & Tools', 'Exp-008', 'Physical items used for work.', 0),
  (9, '2026-03-12 13:03:47.958228', '2026-03-15 11:51:28.150118', 1, 'Transportation & Travel', 'Exp-009', 'Costs related to business movement. like delivery charges', 0),
  (10, '2026-03-12 13:05:09.107953', '2026-03-15 17:00:17.990577', 1, 'Employee Payroll / Labor Costs', 'Exp-010', 'Salaries, Wages, Freelancers, Contractor payments, Employee benefits', 0),
  (11, '2026-03-12 13:07:48.816190', '2026-03-12 13:07:48.816209', 1, 'Professional Services', 'Exp-011', 'Services from experts: Accountant, Lawyer, Consultant, Business coach', 0),
  (12, '2026-03-12 13:09:01.850647', '2026-03-12 13:09:01.850662', 1, 'Taxes & Government Fees', 'Exp-012', 'Mandatory payments: Business tax, Permit fees, Licenses, Registration fees', 0),
  (13, '2026-03-12 13:10:49.896072', '2026-03-12 13:10:49.896089', 1, 'Banking & Payment Fees', 'Exp- 013', 'Financial service costs: Bank charges, Payment gateway fees, Credit card processing fees, Transfer fees', 0),
  (14, '2026-03-12 13:13:23.887683', '2026-03-12 13:13:23.887710', 1, 'Employee Meals / Staff Meals', 'Exp-013', 'snacks & Lunch', 0),
  (15, '2026-03-15 16:27:34.359870', '2026-03-15 16:27:34.359885', 1, 'Shop Development Costs', 'EXP-014', 'Intangible Assets on the balance sheet, because they provide value for more than one year', 0)
ON CONFLICT DO NOTHING;

SELECT setval(pg_get_serial_sequence('core_expensecategory', 'id'), COALESCE((SELECT MAX(id) FROM "core_expensecategory"), 1));
