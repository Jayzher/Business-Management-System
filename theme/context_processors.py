def user_role_flags(request):
    """Expose role flags and role set to all templates."""
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return {'is_view_only': False, 'is_viewer': False, 'user_roles': set()}
    if user.is_superuser:
        return {'is_view_only': False, 'is_viewer': False, 'user_roles': {'Admin'}}
    from accounts.decorators import _user_is_view_only, _user_is_viewer
    roles = set(user.user_roles.values_list('role__name', flat=True))
    return {
        'is_view_only': _user_is_view_only(user),
        'is_viewer': _user_is_viewer(user),
        'user_roles': roles,
    }


_ALL = None  # sentinel: every role can see this item
_VIEWER_ONLY = {'Viewer'}  # Viewer role — catalog read-only

# Role → sidebar module access map.  _ALL means every authenticated user.
# The set values must match accounts.Role.name exactly.
_ADMIN_MANAGER = {'Admin', 'Manager', 'Manager (View Only)'}
_EVERYONE_EXCEPT_VIEWER = {*_ADMIN_MANAGER, 'Procurement Officer', 'Sales Officer', 'Warehouse Staff', 'POS Cashier'}
_ROLE_MAP = {
    'Dashboard':   _EVERYONE_EXCEPT_VIEWER,
    'Catalog':     _ALL,
    'Partners':    {*_ADMIN_MANAGER, 'Procurement Officer', 'Sales Officer'},
    'Warehouses':  {*_ADMIN_MANAGER, 'Procurement Officer', 'Warehouse Staff'},
    'Procurement': {*_ADMIN_MANAGER, 'Procurement Officer'},
    'Sales':       {*_ADMIN_MANAGER, 'Sales Officer'},
    'Expenses':    _ADMIN_MANAGER,
    'Supplies':    {*_ADMIN_MANAGER, 'Warehouse Staff'},
    'Cash Flow':   _ADMIN_MANAGER,
    'Services':    {*_ADMIN_MANAGER, 'Sales Officer'},
    'Inventory':   {*_ADMIN_MANAGER, 'Procurement Officer', 'Warehouse Staff'},
    'POS':         {*_ADMIN_MANAGER, 'POS Cashier', 'Sales Officer'},
    'Pricing':     {*_ADMIN_MANAGER, 'Sales Officer'},
    'QR Codes':    {*_ADMIN_MANAGER, 'Warehouse Staff'},
    'Reports':     {*_ADMIN_MANAGER, 'Sales Officer', 'Procurement Officer'},
    'Target Goals': _ADMIN_MANAGER,
    'Dictionary':  _EVERYONE_EXCEPT_VIEWER,
    'Settings':    {'Admin'},
}


def sidebar_menu(request):
    """Provide sidebar menu items to all templates, filtered by user role."""
    user = getattr(request, 'user', None)
    if user and user.is_authenticated:
        if user.is_superuser:
            user_roles = {'Admin'}
        else:
            user_roles = set(user.user_roles.values_list('role__name', flat=True))
    else:
        user_roles = set()

    menu = [
        {
            'label': 'Dashboard',
            'icon': 'fas fa-tachometer-alt',
            'url': '/dashboard/',
            'active_prefix': '/dashboard',
            'tour_id': 'nav-dashboard',
        },
        {
            'label': 'Catalog',
            'icon': 'fas fa-boxes',
            'tour_id': 'nav-catalog',
            'children': [
                {'label': 'Items', 'url': '/catalog/items/', 'active_prefix': '/catalog/items', 'icon': 'fas fa-box'},
                {'label': 'Categories', 'url': '/catalog/categories/', 'active_prefix': '/catalog/categories', 'icon': 'fas fa-sitemap'},
                {'label': 'Units', 'url': '/catalog/units/', 'active_prefix': '/catalog/units', 'icon': 'fas fa-ruler-combined'},
                {'label': 'Unit Conversions', 'url': '/catalog/unit-conversions/', 'active_prefix': '/catalog/unit-conversions', 'icon': 'fas fa-exchange-alt'},
            ],
        },
        {
            'label': 'Partners',
            'icon': 'fas fa-handshake',
            'tour_id': 'nav-partners',
            'children': [
                {'label': 'Suppliers', 'url': '/partners/suppliers/', 'active_prefix': '/partners/suppliers', 'icon': 'fas fa-truck-moving'},
                {'label': 'Customers', 'url': '/partners/customers/', 'active_prefix': '/partners/customers', 'icon': 'fas fa-user-friends'},
            ],
        },
        {
            'label': 'Warehouses',
            'icon': 'fas fa-warehouse',
            'tour_id': 'nav-warehouses',
            'children': [
                {'label': 'Warehouses', 'url': '/warehouses/', 'active_prefix': '/warehouses', 'icon': 'fas fa-warehouse'},
                {'label': 'Locations', 'url': '/warehouses/locations/', 'active_prefix': '/warehouses/locations', 'icon': 'fas fa-map-marker-alt'},
            ],
        },
        {
            'label': 'Procurement',
            'icon': 'fas fa-truck-loading',
            'tour_id': 'nav-procurement',
            'children': [
                {'label': 'Purchase Orders', 'url': '/procurement/purchase-orders/', 'active_prefix': '/procurement/purchase-orders', 'icon': 'fas fa-clipboard-list'},
                {'label': 'Goods Receipts', 'url': '/procurement/goods-receipts/', 'active_prefix': '/procurement/goods-receipts', 'icon': 'fas fa-inbox'},
                {'label': 'Purchase Returns', 'url': '/procurement/purchase-returns/', 'active_prefix': '/procurement/purchase-returns', 'icon': 'fas fa-undo-alt'},
                {'label': 'Supplier Catalog', 'url': '/procurement/supplier-catalog/', 'active_prefix': '/procurement/supplier-catalog', 'icon': 'fas fa-balance-scale'},
            ],
        },
        {
            'label': 'Sales',
            'icon': 'fas fa-shopping-cart',
            'tour_id': 'nav-sales',
            'children': [
                {'label': 'Sales Orders', 'url': '/sales/orders/', 'active_prefix': '/sales/orders', 'icon': 'fas fa-file-invoice'},
                {'label': 'Deliveries', 'url': '/sales/deliveries/', 'active_prefix': '/sales/deliveries', 'icon': 'fas fa-shipping-fast'},
                {'label': 'Pickups', 'url': '/sales/pickups/', 'active_prefix': '/sales/pickups', 'icon': 'fas fa-shopping-basket'},
                {'label': 'Sales Returns', 'url': '/sales/returns/', 'active_prefix': '/sales/returns', 'icon': 'fas fa-undo'},
                {'label': 'Invoices', 'url': '/core/invoices/', 'active_prefix': '/core/invoices', 'icon': 'fas fa-file-invoice-dollar'},
                {'label': 'Sales Channels', 'url': '/core/channels/', 'active_prefix': '/core/channels', 'icon': 'fas fa-bullhorn'},
            ],
        },
        {
            'label': 'Expenses',
            'icon': 'fas fa-receipt',
            'tour_id': 'nav-expenses',
            'children': [
                {'label': 'Expense Listing', 'url': '/core/expenses/', 'active_prefix': '/core/expenses', 'icon': 'fas fa-list-alt'},
                {'label': 'Expense Categories', 'url': '/core/expense-categories/', 'active_prefix': '/core/expense-categories', 'icon': 'fas fa-layer-group'},
            ],
        },
        {
            'label': 'Supplies',
            'icon': 'fas fa-box-open',
            'tour_id': 'nav-supplies',
            'children': [
                {'label': 'Supply Items', 'url': '/core/supplies/', 'active_prefix': '/core/supplies', 'icon': 'fas fa-box-open'},
                {'label': 'Movements', 'url': '/core/supply-movements/', 'active_prefix': '/core/supply-movements', 'icon': 'fas fa-exchange-alt'},
                {'label': 'Supply Categories', 'url': '/core/supply-categories/', 'active_prefix': '/core/supply-categories', 'icon': 'fas fa-tags'},
            ],
        },
        {
            'label': 'Cash Flow',
            'icon': 'fas fa-money-bill-wave',
            'tour_id': 'nav-cashflow',
            'children': [
                {'label': 'Transactions', 'url': '/cashflow/', 'active_prefix': '/cashflow/', 'icon': 'fas fa-exchange-alt'},
                {'label': 'Logs', 'url': '/cashflow/logs/', 'active_prefix': '/cashflow/logs', 'icon': 'fas fa-history'},
            ],
        },
        {
            'label': 'Services',
            'icon': 'fas fa-tools',
            'tour_id': 'nav-services',
            'children': [
                {'label': 'Customer Services', 'url': '/services/', 'active_prefix': '/services/', 'icon': 'fas fa-clipboard-check'},
                {'label': 'Service Invoices', 'url': '/services/invoices/', 'active_prefix': '/services/invoices', 'icon': 'fas fa-file-invoice-dollar'},
            ],
        },
        {
            'label': 'Inventory',
            'icon': 'fas fa-exchange-alt',
            'tour_id': 'nav-inventory',
            'children': [
                {'label': 'Item Inventory', 'url': '/inventory/inventory/', 'active_prefix': '/inventory/inventory', 'icon': 'fas fa-boxes'},
                {'label': 'Stock Movements', 'url': '/inventory/moves/', 'active_prefix': '/inventory/moves', 'icon': 'fas fa-sync-alt'},
                {'label': 'Transfers', 'url': '/inventory/transfers/', 'active_prefix': '/inventory/transfers', 'icon': 'fas fa-random'},
                {'label': 'Adjustments', 'url': '/inventory/adjustments/', 'active_prefix': '/inventory/adjustments', 'icon': 'fas fa-sliders-h'},
                {'label': 'Damaged Stock', 'url': '/inventory/damaged/', 'active_prefix': '/inventory/damaged', 'icon': 'fas fa-ban'},
                {'label': 'Inv → Supply', 'url': '/inventory/supply-transfers/', 'active_prefix': '/inventory/supply-transfers', 'icon': 'fas fa-sign-in-alt'},
            ],
        },
        {
            'label': 'POS',
            'icon': 'fas fa-cash-register',
            'tour_id': 'nav-pos',
            'children': [
                {'label': 'Registers', 'url': '/pos/registers/', 'active_prefix': '/pos/registers', 'icon': 'fas fa-cash-register'},
                {'label': 'Shifts', 'url': '/pos/shifts/', 'active_prefix': '/pos/shifts', 'icon': 'fas fa-history'},
                {'label': 'Receipts', 'url': '/pos/receipts/', 'active_prefix': '/pos/receipts', 'icon': 'fas fa-receipt'},
            ],
        },
        {
            'label': 'Pricing',
            'icon': 'fas fa-tags',
            'tour_id': 'nav-pricing',
            'children': [
                {'label': 'Price Lists', 'url': '/pricing/price-lists/', 'active_prefix': '/pricing/price-lists', 'icon': 'fas fa-tag'},
                {'label': 'Discount Rules', 'url': '/pricing/discount-rules/', 'active_prefix': '/pricing/discount-rules', 'icon': 'fas fa-percent'},
                {'label': 'Customer Catalogs', 'url': '/pricing/customer-catalogs/', 'active_prefix': '/pricing/customer-catalogs', 'icon': 'fas fa-user-tag'},
            ],
        },
        {
            'label': 'QR Codes',
            'icon': 'fas fa-qrcode',
            'tour_id': 'nav-qr',
            'children': [
                {'label': 'QR Tags', 'url': '/qr/', 'active_prefix': '/qr/', 'icon': 'fas fa-qrcode'},
                {'label': 'Scan', 'url': '/qr/scan/', 'active_prefix': '/qr/scan', 'icon': 'fas fa-camera'},
                {'label': 'Print Labels', 'url': '/qr/print/', 'active_prefix': '/qr/print', 'icon': 'fas fa-print'},
            ],
        },
        {
            'label': 'Reports',
            'icon': 'fas fa-chart-bar',
            'tour_id': 'nav-reports',
            'children': [
                {'label': 'Reports Hub', 'url': '/reports/', 'active_prefix': '/reports/', 'icon': 'fas fa-chart-pie'},
                {'label': 'Sales Report', 'url': '/reports/sales/', 'active_prefix': '/reports/sales', 'icon': 'fas fa-chart-line'},
                {'label': 'Expense Report', 'url': '/reports/expenses/', 'active_prefix': '/reports/expenses', 'icon': 'fas fa-wallet'},
                {'label': 'Financial Statement', 'url': '/reports/financial-statement/', 'active_prefix': '/reports/financial-statement', 'icon': 'fas fa-file-invoice-dollar'},
                {'label': 'Profit Margin', 'url': '/reports/profit-margin/', 'active_prefix': '/reports/profit-margin', 'icon': 'fas fa-chart-area'},
                {'label': 'Stock On Hand', 'url': '/reports/stock-on-hand/', 'active_prefix': '/reports/stock-on-hand', 'icon': 'fas fa-boxes'},
                {'label': 'Low Stock', 'url': '/reports/low-stock/', 'active_prefix': '/reports/low-stock', 'icon': 'fas fa-exclamation-triangle'},
                {'label': 'Stock Aging', 'url': '/reports/stock-aging/', 'active_prefix': '/reports/stock-aging', 'icon': 'fas fa-clock'},
            ],
        },
        {
            'label': 'Target Goals',
            'icon': 'fas fa-bullseye',
            'url': '/core/goals/',
            'active_prefix': '/core/goals',
            'tour_id': 'nav-goals',
        },
        {
            'label': 'Dictionary',
            'icon': 'fas fa-book',
            'url': '/core/dictionary/',
            'active_prefix': '/core/dictionary',
            'tour_id': 'nav-dictionary',
        },
        {
            'label': 'Settings',
            'icon': 'fas fa-cog',
            'tour_id': 'nav-settings',
            'children': [
                {'label': 'Business Profile', 'url': '/core/settings/', 'active_prefix': '/core/settings/', 'icon': 'fas fa-building'},
                {'label': 'User Management', 'url': '/accounts/users/', 'active_prefix': '/accounts/users', 'icon': 'fas fa-users-cog'},
                {'label': 'Roles', 'url': '/accounts/roles/', 'active_prefix': '/accounts/roles', 'icon': 'fas fa-user-tag'},
                {'label': 'System Logs', 'url': '/audit/system/', 'active_prefix': '/audit/system', 'icon': 'fas fa-history'},
                {'label': 'Manual Logs', 'url': '/audit/manual/', 'active_prefix': '/audit/manual', 'icon': 'fas fa-pen-square'},
                {'label': 'Tests & Syncs', 'url': '/core/settings/tests-syncs/', 'active_prefix': '/core/settings/tests-syncs', 'icon': 'fas fa-vial'},
            ],
        },
    ]

    # ── Filter menu by user role ────────────────────────────────────────
    if user_roles:
        filtered = []
        for item in menu:
            allowed = _ROLE_MAP.get(item['label'], _ALL)
            if allowed is _ALL or user_roles & allowed:
                filtered.append(item)
        menu = filtered

    # Mark active items
    path = request.path if hasattr(request, 'path') else ''
    for item in menu:
        if 'children' in item:
            item['is_open'] = False
            # Pick the most specific matching child (longest active_prefix)
            matches = [c for c in item['children'] if path.startswith(c.get('active_prefix', ''))]
            if matches:
                best = max(matches, key=lambda c: len(c.get('active_prefix', '')))
                for child in item['children']:
                    child['is_active'] = child is best
                item['is_open'] = True
            else:
                for child in item['children']:
                    child['is_active'] = False
        else:
            item['is_active'] = path.startswith(item.get('active_prefix', ''))

    return {'sidebar_menu': menu}
