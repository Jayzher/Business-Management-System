# Web Version Role Implementation

## Overview
This document describes the implementation of the "Web Version" role in the Business Management System.

## Role Characteristics
The **Web Version** role provides:
- **Read-only access** to all modules EXCEPT:
  - Adjustments (Stock Adjustments)
  - POS (Point of Sale)
- **No Create/Edit/Delete permissions** - all write operations are blocked
- Full visibility of data across the system for viewing and reporting purposes

## Implementation Details

### 1. Role Definition
- **File**: `core/management/commands/seed_roles.py`
- **Added**: New "Web Version" role to the DEFAULT_ROLES list
- **Description**: "Read-only access to all modules except Adjustments and POS. Cannot create, edit, delete, or post any records."

### 2. Permission Decorators
- **File**: `accounts/decorators.py`
- **Added**: `_user_is_web_version()` helper function to check if user has only Web Version role
- **Updated**: `write_denied_for_viewer()` decorator to also block Web Version users from write operations
- **Created**: `adjustment_access()` decorator specifically for adjustment views (excludes Web Version)
- **Updated**: All access decorators to include Web Version except:
  - `adjustment_access()` - excludes Web Version
  - `pos_access()` - excludes Web Version

### 3. Context Processor
- **File**: `theme/context_processors.py`
- **Added**: `is_web_version` flag exposed to all templates
- **Updated**: Sidebar menu role map to include Web Version for all modules except POS
- **Added**: Special filtering logic to remove "Adjustments" submenu from Inventory module for Web Version users
- **Module Access**: Web Version can see:
  - Dashboard, Catalog, Partners, Warehouses, Procurement, Sales
  - Expenses, Supplies, Cash Flow, Services, Inventory (Transfers, Damaged, IST only - Adjustments hidden)
  - Pricing, QR Codes, Reports, Target Goals, Dictionary

### 4. Template Updates
- **Files**: 35 template files updated
- **Change**: All `{% if not is_view_only %}` checks updated to `{% if not is_view_only and not is_web_version %}`
- **Effect**: Hides all Create, Edit, Delete, Approve, Post, and Cancel buttons for Web Version users
- **Templates Updated**:
  - Cashflow, Catalog, Core, Inventory, Partners, POS, Pricing
  - Procurement, Sales, Services, Warehouses modules
  - Document action partial (`theme/partials/doc_actions.html`)

### 5. View Protection
- **File**: `inventory/views.py`
- **Updated**: All adjustment-related views to use `@adjustment_access` decorator
- **Views Protected**:
  - `adjustment_list_view` - can view list but no access to create
  - `adjustment_detail_view` - can view details but no action buttons
  - `adjustment_create_view` - blocked
  - `adjustment_edit_view` - blocked
  - `adjustment_delete_view` - blocked
  - `adjustment_approve_view` - blocked
  - `adjustment_post_view` - blocked
  - `adjustment_cancel_view` - blocked

### 6. Role Display
- **File**: `accounts/views.py`
- **Updated**: ROLE_MODULES dictionary to include Web Version
- **Display**: "All modules except Adjustments & POS, NO write actions"

## Access Matrix

| Module | Web Version Access |
|--------|-------------------|
| Dashboard | ✅ View Only |
| Catalog | ✅ View Only |
| Partners | ✅ View Only |
| Warehouses | ✅ View Only |
| Procurement | ✅ View Only |
| Sales | ✅ View Only |
| Expenses | ✅ View Only |
| Supplies | ✅ View Only |
| Cash Flow | ✅ View Only |
| Services | ✅ View Only |
| Inventory | ✅ View Only (Transfers, Damaged, IST) |
| **Adjustments** | ❌ No Access |
| **POS** | ❌ No Access |
| Pricing | ✅ View Only |
| QR Codes | ✅ View Only |
| Reports | ✅ View Only |
| Target Goals | ✅ View Only |
| Dictionary | ✅ View Only |
| Settings | ❌ No Access |

## Deployment Steps

1. **Run migrations** (if any database changes were made)
2. **Seed the new role**:
   ```bash
   python manage.py seed_roles
   ```
3. **Assign users** to the Web Version role through the admin interface
4. **Test access** by logging in as a Web Version user and verifying:
   - All modules are visible except Adjustments and POS
   - No Create/Edit/Delete buttons appear
   - All write operations are blocked with appropriate error messages

## Testing Checklist

- [ ] Web Version user can log in successfully
- [ ] Dashboard is accessible
- [ ] All modules appear in sidebar except Adjustments and POS
- [ ] No Create buttons visible in any list view
- [ ] No Edit/Delete buttons visible in any list view
- [ ] Detail views show data but no action buttons
- [ ] Attempting direct URL access to create/edit/delete views shows error
- [ ] Adjustments module is not accessible (redirected with error)
- [ ] POS module is not accessible (redirected with error)
- [ ] Reports can be viewed and exported
- [ ] Print functionality works for documents

## Notes

- The Web Version role is designed for external users who need visibility into the system without the ability to make changes
- This role is ideal for clients, auditors, or stakeholders who need reporting access
- All write operations are blocked at both the template level (UI) and view level (backend)
- The role follows the same security pattern as "Manager (View Only)" but with restricted module access
