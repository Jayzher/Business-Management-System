def sidebar_menu(request):
    """Provide sidebar menu items to all templates."""
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
                {'label': 'Locations', 'url': '/warehouses/locations/', 'active_prefix': '/warehouses/locations', 'icon': 'fas fa-location-dot'},
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
            ],
        },
        {
            'label': 'Sales',
            'icon': 'fas fa-shopping-cart',
            'tour_id': 'nav-sales',
            'children': [
                {'label': 'Sales Orders', 'url': '/sales/orders/', 'active_prefix': '/sales/orders', 'icon': 'fas fa-file-invoice'},
                {'label': 'Deliveries', 'url': '/sales/deliveries/', 'active_prefix': '/sales/deliveries', 'icon': 'fas fa-truck-fast'},
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
                {'label': 'Expense Listing', 'url': '/core/expenses/', 'active_prefix': '/core/expenses', 'icon': 'fas fa-clipboard-list-check'},
                {'label': 'Expense Categories', 'url': '/core/expense-categories/', 'active_prefix': '/core/expense-categories', 'icon': 'fas fa-layer-group'},
            ],
        },
        {
            'label': 'Supplies',
            'icon': 'fas fa-box-open',
            'tour_id': 'nav-supplies',
            'children': [
                {'label': 'Supply Items', 'url': '/core/supplies/', 'active_prefix': '/core/supplies', 'icon': 'fas fa-box-open'},
                {'label': 'Movements', 'url': '/core/supply-movements/', 'active_prefix': '/core/supply-movements', 'icon': 'fas fa-right-left'},
                {'label': 'Supply Categories', 'url': '/core/supply-categories/', 'active_prefix': '/core/supply-categories', 'icon': 'fas fa-tags'},
            ],
        },
        {
            'label': 'Inventory',
            'icon': 'fas fa-exchange-alt',
            'tour_id': 'nav-inventory',
            'children': [
                {'label': 'Item Inventory', 'url': '/inventory/inventory/', 'active_prefix': '/inventory/inventory', 'icon': 'fas fa-boxes'},
                {'label': 'Stock Movements', 'url': '/inventory/moves/', 'active_prefix': '/inventory/moves', 'icon': 'fas fa-arrows-rotate'},
                {'label': 'Transfers', 'url': '/inventory/transfers/', 'active_prefix': '/inventory/transfers', 'icon': 'fas fa-right-left'},
                {'label': 'Adjustments', 'url': '/inventory/adjustments/', 'active_prefix': '/inventory/adjustments', 'icon': 'fas fa-sliders-h'},
                {'label': 'Damaged Stock', 'url': '/inventory/damaged/', 'active_prefix': '/inventory/damaged', 'icon': 'fas fa-ban'},
            ],
        },
        {
            'label': 'POS',
            'icon': 'fas fa-cash-register',
            'tour_id': 'nav-pos',
            'children': [
                {'label': 'Registers', 'url': '/pos/registers/', 'active_prefix': '/pos/registers', 'icon': 'fas fa-cash-register'},
                {'label': 'Shifts', 'url': '/pos/shifts/', 'active_prefix': '/pos/shifts', 'icon': 'fas fa-clock-rotate-left'},
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
                {'label': 'Stock On Hand', 'url': '/reports/stock-on-hand/', 'active_prefix': '/reports/stock-on-hand', 'icon': 'fas fa-boxes-stacked'},
                {'label': 'Low Stock', 'url': '/reports/low-stock/', 'active_prefix': '/reports/low-stock', 'icon': 'fas fa-triangle-exclamation'},
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
            'url': '/core/settings/',
            'active_prefix': '/core/settings',
            'tour_id': 'nav-settings',
        },
    ]

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
