-- Table: core_supplyitem (27 rows)
-- Paste this into Neon SQL Editor

INSERT INTO "core_supplyitem" ("id", "created_at", "updated_at", "is_active", "name", "code", "unit", "cost_per_unit", "current_stock", "minimum_stock", "category_id", "low_stock_alert_level", "notes", "supplier_brand", "units_per_piece") VALUES
  (204, '2026-03-23 13:35:03.818275', '2026-03-23 13:46:05.262911', 0, 'Stanley Hinges', 'SVC-MTRL-HINGES', 'pcs', 65, 2, 1, NULL, 0, '', 'StNLEY', 2),
  (205, '2026-03-23 13:39:44.825867', '2026-03-23 13:46:01.821563', 0, 'Doorknob', 'SVC-ACCE-Doorknob', 'pcs', 170, 2, 1, 3, 0, '', '', 1),
  (206, '2026-03-23 14:44:24.398918', '2026-03-27 04:02:08.763643', 1, 'Silicone GP Clear', 'ADH-GP-c', 'pcs', 101.2113, 5, 0, NULL, 0, 'Auto-created from inventory item ADH-GP-c', '', 1),
  (207, '2026-03-23 14:44:24.402089', '2026-03-27 03:56:39.091714', 1, 'SQ Tube 1x1 Anodized', 'TUB-1X1-A', 'pcs', 280, 7, 0, NULL, 0, 'Auto-created from inventory item TUB-1X1-A', '', 1),
  (208, '2026-03-23 14:44:24.404603', '2026-03-27 03:57:54.506714', 1, 'Rectangular Tube 1x4 Analok', 'TUB-1X4-HA', 'pcs', 960, 1, 0, NULL, 0, 'Auto-created from inventory item TUB-1X4-HA', '', 1),
  (209, '2026-03-23 14:44:24.407075', '2026-03-27 03:57:46.857927', 1, 'Rectangular Tube 1x2 PCW', 'TUB-1X2-PCW', 'pcs', 442.8657, 2, 0, NULL, 0, 'Auto-created from inventory item TUB-1X2-PCW', '', 1),
  (210, '2026-03-23 14:44:24.409594', '2026-03-27 03:57:38.495883', 1, 'Rectangular Tube 1x1-1/2 PCW', 'TUB-1X1-1/2-PCW', 'pcs', 400, 1, 0, NULL, 0, 'Auto-created from inventory item TUB-1X1-1/2-PCW', '', 1),
  (211, '2026-03-23 14:44:24.412039', '2026-03-27 03:57:30.682879', 1, 'Rectangular Tube 1x3 Powdercoat', 'TUB-1X3-PCW', 'pcs', 618.7912, 1, 0, NULL, 0, 'Auto-created from inventory item TUB-1X3-PCW', '', 1),
  (212, '2026-03-23 14:44:24.414775', '2026-03-27 03:57:19.343178', 1, 'SQ Tube 1-3/4x1-3/4 Powdercoat', 'TUB-1-3/4X1-3/4-PCW', 'pcs', 603, 1, 0, NULL, 0, 'Auto-created from inventory item TUB-1-3/4X1-3/4-PCW', '', 1),
  (213, '2026-03-23 14:44:24.417382', '2026-03-27 03:57:09.563816', 1, 'SQ Tube 1x1 Powdercoat', 'TUB-1X1-PCW', 'pcs', 286, 1, 0, NULL, 0, 'Auto-created from inventory item TUB-1X1-PCW', '', 1),
  (214, '2026-03-23 14:44:24.419864', '2026-03-27 03:56:49.313513', 1, '3mm Glossy White-one Sided Cladding 4X8ft', 'CLA-4X8-GS', 'pcs', 1035, 1, 0, NULL, 0, 'Auto-created from inventory item CLA-4X8-GS', '', 1),
  (215, '2026-03-23 14:50:54.759829', '2026-03-27 03:54:42.464929', 1, '6mm Clear 72x96', 'GLA-72X96-C', 'sht', 1392, 0, 0, NULL, 0, 'Auto-created from inventory item GLA-72X96-C', '', 1),
  (216, '2026-03-23 14:50:54.762786', '2026-03-30 09:11:58.128296', 1, '5mm Clear 48x72', 'GLA-48X72-Clear', 'sht', 528, 0, 0, NULL, 0, 'Auto-created from inventory item GLA-48X72-Clear', '', 1),
  (217, '2026-03-23 15:05:09.713199', '2026-03-27 04:01:02.449087', 1, '3mm JL Clad White S', 'CLA-JL-W-S', 'pcs', 798.75, 0, 0, NULL, 0, 'Auto-created from inventory item CLA-JL-W-S', '', 1),
  (218, '2026-03-23 15:05:09.717942', '2026-03-27 04:03:14.128907', 1, 'Rectangular Tube 1/2x1 Powdercoat', 'TUB-1/2X1-P', 'pcs', 235, 0, 0, NULL, 0, 'Auto-created from inventory item TUB-1/2X1-P', '', 1),
  (219, '2026-03-23 15:05:09.720494', '2026-03-27 04:04:13.852870', 1, 'Angular 1/2x1/2x1/16 (12ft)-PCW', 'Angular 1/2x1/2x1/16 (12ft)-PCW', 'pcs', 88, 0, 0, NULL, 0, 'Auto-created from inventory item Angular 1/2x1/2x1/16 (12ft)-PCW', '', 1),
  (220, '2026-03-23 15:05:09.723283', '2026-03-27 04:05:11.885113', 1, 'Wood Screw 12x3 Anodize', 'SCREW-12X3-WS-A', 'pcs', 1.8, 0, 0, NULL, 0, 'Auto-created from inventory item SCREW-12X3-WS-A', '', 1),
  (221, '2026-03-23 15:52:05.435656', '2026-03-30 15:13:05.883316', 1, 'sharpening stone', 'Tools-001', 'pcs', 250, 0, 0, NULL, 0, '', '', 1),
  (222, '2026-03-24 05:52:47.671434', '2026-03-27 04:08:54.480558', 1, 'Drawer slide guide #14', 'ACC-DSG-#14', 'pcs', 79, 0, 0, NULL, 0, 'Auto-created from inventory item ACC-DSG-#14', '', 1),
  (223, '2026-03-24 05:52:47.676847', '2026-03-27 04:09:57.936843', 1, 'Bended PCW', 'ACC-Ben-PCW', 'pcs', 16, 0, 0, NULL, 0, 'Auto-created from inventory item ACC-Ben-PCW', '', 1),
  (224, '2026-03-24 05:52:47.679517', '2026-03-27 04:11:10.235686', 1, 'METAL SCREW ANODIZE 8x2 Anodize', 'SCREW-8x2-M/S-A', 'GRS', 120, 0, 0, NULL, 0, 'Auto-created from inventory item SCREW-8x2-M/S-A', '', 1),
  (225, '2026-03-24 05:52:47.682452', '2026-03-27 04:13:45.615701', 1, 'Angle 1-1/2x1-1/2x1/8 Mill Finished/Anodized', 'BRA-1-1/2X1-1/2-A', 'pcs', 566, 0, 0, NULL, 0, 'Auto-created from inventory item BRA-1-1/2X1-1/2-A', '', 1),
  (226, '2026-03-24 05:52:47.687716', '2026-03-27 04:12:52.108436', 1, '1/4 Power Craft High Speed HSS Drill Bits', 'TOO-1/4-DrillB', 'pcs', 79.9, 1, 0, NULL, 0, 'Auto-created from inventory item TOO-1/4-DrillB', '', 1),
  (227, '2026-03-24 06:42:23.055898', '2026-03-24 06:42:23.061891', 1, 'Glass Cutter', 'TOO-Gcut', 'pcs', 150, 1, 0, NULL, 0, 'Auto-created from inventory item TOO-Gcut', '', 1),
  (228, '2026-03-30 15:09:59.326721', '2026-03-30 15:12:48.636977', 1, 'Miter saw', 'Equip-001', 'pcs', 5373, 0, 0, NULL, 0, '', '', 1),
  (229, '2026-03-30 15:11:28.618311', '2026-03-30 15:12:08.091869', 1, 'Akita Scale', 'Equip-002', 'pcs', 1450, 0, 0, NULL, 0, '', '', 1),
  (230, '2026-03-30 15:14:43.993918', '2026-03-30 15:14:43.993996', 1, 'rope 10 meters', 'Tools-004', 'm', 16, 0, 0, NULL, 0, '10 meters', '', 1)
ON CONFLICT DO NOTHING;

SELECT setval(pg_get_serial_sequence('core_supplyitem', 'id'), COALESCE((SELECT MAX(id) FROM "core_supplyitem"), 1));
