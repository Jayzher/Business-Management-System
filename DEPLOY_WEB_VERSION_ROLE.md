# Deploy Web Version & Checker Roles - Quick Guide

## Overview
This guide covers deployment of two read-only roles:
- **Web Version**: Read-only access to all modules except Adjustments & POS
- **Checker**: Same as Web Version (read-only, no Adjustments/POS access)

Both roles have identical permissions and are treated the same by the system.

## Step 1: Seed the Roles
Run this command to create the "Web Version" and "Checker" roles in the database:

```bash
python manage.py seed_roles
```

Expected output:
```
  Role already exists: Admin
  Created role: Manager
  Created role: Manager (View Only)
  Created role: Procurement Officer
  Created role: Sales Officer
  Created role: Warehouse Staff
  Created role: POS Cashier
  Role already exists: Viewer
  Role already exists: Web Version
  Role already exists: Checker
  Role already exists: Encoder
  Role already exists: Warehouse Manager

Done. X new roles created.
```

## Step 2: Assign Users to Web Version or Checker Role

### Option A: Using Django Admin
1. Go to `/admin/accounts/userrole/`
2. Click "Add User Role"
3. Select the user
4. Select "Web Version" or "Checker" role
5. Save

### Option B: Using the User Management Interface
1. Go to Settings → Users
2. Click on a user
3. Assign "Web Version" or "Checker" role
4. Save

**Note**: Both roles have identical permissions. Use "Checker" for internal staff and "Web Version" for external users.

## Step 3: Test the Implementation

### Test 1: Login and Navigation
- [ ] Log in as a Web Version or Checker user
- [ ] Verify Dashboard is accessible
- [ ] Check sidebar menu - should see all modules except "POS"
- [ ] Verify "Adjustments" submenu is NOT in Inventory dropdown

### Test 2: Module Access
- [ ] Try accessing Catalog - should work (view only)
- [ ] Try accessing Procurement - should work (view only)
- [ ] Try accessing Sales - should work (view only)
- [ ] Try accessing Inventory - should work (view only)
- [ ] **Verify "Adjustments" submenu is NOT visible in Inventory dropdown**
- [ ] Try accessing `/inventory/adjustment/` directly - should be redirected with error
- [ ] Try accessing `/pos/` - should be redirected with error

### Test 3: Write Operations Blocked
- [ ] Go to any list view (e.g., Purchase Orders)
- [ ] Verify NO "New PO" or "Create" buttons visible
- [ ] Open a document detail view
- [ ] Verify NO Edit/Delete/Approve/Post buttons visible
- [ ] Try direct URL access to create view (e.g., `/procurement/purchase-order/create/`)
- [ ] Should see error: "Your role is view-only. You cannot make changes."

### Test 4: Reports and Exports
- [ ] Access Reports module
- [ ] Generate a report
- [ ] Verify export functionality works
- [ ] Verify print functionality works

## Rollback (if needed)

If you need to rollback the changes:

1. Remove Web Version/Checker role assignments from users
2. Delete the roles from database:
```python
from accounts.models import Role
Role.objects.filter(name__in=['Web Version', 'Checker']).delete()
```

## Troubleshooting

### Issue: User can still see Create buttons
**Solution**: Clear browser cache and refresh the page. The template changes require a fresh page load.

### Issue: User gets "Permission Denied" on all pages
**Solution**: Verify the user has ONLY the "Web Version" or "Checker" role assigned, not multiple roles.

### Issue: Adjustments still accessible
**Solution**: Restart the Django server to reload the decorator changes:
```bash
python manage.py runserver
```

### Issue: Role not appearing in dropdown
**Solution**: Run `python manage.py seed_roles` again and verify the role was created.

## Summary of Changes

**Files Modified**: 40+ files
- 1 role definition file (added Web Version, Checker, Encoder, Warehouse Manager)
- 2 decorator/permission files  
- 2 context processor files
- 35 template files
- 1 views file (inventory)

**Key Features**:
- ✅ Read-only access to all modules except Adjustments & POS
- ✅ All Create/Edit/Delete buttons hidden
- ✅ Backend protection against direct URL access
- ✅ Consistent with existing role-based access control patterns
- ✅ No database migrations required
- ✅ Both Web Version and Checker roles work identically

**Current Users**:
- Joy-A, Jayzee, joy: Checker role
- web_version_test: Web Version role

## Support

For issues or questions, refer to:
- `WEB_VERSION_ROLE_IMPLEMENTATION.md` - Technical documentation
- `CHECKER_ROLE_IMPLEMENTATION_SUMMARY.md` - Complete implementation summary
