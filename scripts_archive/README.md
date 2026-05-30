# Archived Scripts

This directory contains old scripts that were used for one-time fixes, migrations, or diagnostics. They are kept for historical reference but are no longer needed for regular operations.

## Categories

### Analysis & Diagnostics
- `analyze_discrepancies.py` - Analyzed data discrepancies
- `analyze_january_2026.py` - January 2026 data analysis
- `audit_data_integrity.py` - Data integrity audit
- `audit_stock_integrity.py` - Stock integrity audit
- `diagnose_acc_e_48_ha.py` - Diagnosed specific account issue
- `diagnose_ghost_inventory.py` - Diagnosed ghost inventory issue

### Checks & Verification
- `check_april_2026.py` - April 2026 data check
- `check_april_collections.py` - April collections check
- `check_ar_collections.py` - AR collections check
- `check_capital_transactions.py` - Capital transactions check
- `check_conversions.py` - Unit conversions check
- `check_invoice_payments.py` - Invoice payments check
- `final_verification.py` - Final verification script
- `verify_fixes.py` - Verified applied fixes

### Fixes & Migrations
- `fix_acc_e_48_ha.py` - Fixed specific account issue
- `fix_conversion_issue.py` - Fixed conversion issue
- `fix_database_lock.ps1` - Fixed database lock issue
- `fix_inventory_bugs.py` - Fixed inventory bugs
- `fix_orphaned_fks.py` - Fixed orphaned foreign keys
- `recalculate_service_invoice_cogs.py` - Recalculated service invoice COGS

### Database Operations
- `checkpoint_wal.py` - WAL checkpoint operations
- `delete_neon_conversion.py` - Deleted Neon conversion data
- `export_for_neon.py` - Exported data for Neon
- `load_neon.py` - Loaded Neon data
- `migrate_to_neon.py` - Migrated to Neon database
- `sync_neon_to_local.py` - Synced Neon to local database

### Utilities
- `find_blank_grn_prices.py` - Found blank GRN prices
- `find_existing_conversion.py` - Found existing conversions
- `quick_sync_conversions.py` - Quick sync for conversions
- `run_server.py` - Old server runner (replaced by manage.py runserver)

### Tests
- `test_conversion_issue.py` - Tested conversion issue
- `test_import_summary.py` - Tested import summary

## Status

All scripts in this directory are:
- ✅ No longer needed for regular operations
- ✅ Kept for historical reference
- ✅ May contain useful patterns for future fixes
- ⚠️ Not maintained or updated

## If You Need to Use These

1. Review the script carefully
2. Check if the issue still exists
3. Test in development environment first
4. Consider if a management command would be better

## Archive Date

2026-05-31
