from django.urls import path
from core import views
from core import import_views

urlpatterns = [
    # Settings
    path('settings/', views.settings_view, name='settings'),

    # Sales Channels
    path('channels/', views.channel_list, name='channel_list'),
    path('channels/new/', views.channel_create, name='channel_create'),
    path('channels/<int:pk>/edit/', views.channel_edit, name='channel_edit'),
    path('channels/<int:pk>/delete/', views.channel_delete, name='channel_delete'),

    # Expense Categories
    path('expense-categories/', views.expense_category_list, name='expense_category_list'),
    path('expense-categories/new/', views.expense_category_create, name='expense_category_create'),
    path('expense-categories/<int:pk>/edit/', views.expense_category_edit, name='expense_category_edit'),
    path('expense-categories/<int:pk>/delete/', views.expense_category_delete, name='expense_category_delete'),

    # Expenses
    path('expenses/', views.expense_list, name='expense_list'),
    path('expenses/new/', views.expense_create, name='expense_create'),
    path('expenses/<int:pk>/edit/', views.expense_edit, name='expense_edit'),
    path('expenses/<int:pk>/delete/', views.expense_delete, name='expense_delete'),

    # Invoices
    path('invoices/', views.invoice_list, name='invoice_list'),
    path('invoices/from-sale/<int:sale_id>/', views.invoice_from_sale, name='invoice_from_sale'),
    path('invoices/from-so/<int:so_id>/', views.invoice_from_so, name='invoice_from_so'),
    path('invoices/<int:pk>/', views.invoice_detail, name='invoice_detail'),
    path('invoices/<int:pk>/print/', views.invoice_print, name='invoice_print'),
    path('invoices/<int:pk>/add-payment/', views.invoice_add_payment, name='invoice_add_payment'),
    path('invoices/<int:pk>/mark-paid/', views.invoice_mark_paid, name='invoice_mark_paid'),

    # Supply Categories
    path('supply-categories/', views.supply_category_list, name='supply_category_list'),
    path('supply-categories/new/', views.supply_category_create, name='supply_category_create'),
    path('supply-categories/<int:pk>/edit/', views.supply_category_edit, name='supply_category_edit'),
    path('supply-categories/<int:pk>/delete/', views.supply_category_delete, name='supply_category_delete'),

    # Supply Items
    path('supplies/', views.supply_item_list, name='supply_item_list'),
    path('supplies/new/', views.supply_item_create, name='supply_item_create'),
    path('supplies/<int:pk>/edit/', views.supply_item_edit, name='supply_item_edit'),
    path('supplies/<int:pk>/delete/', views.supply_item_delete, name='supply_item_delete'),

    # Supply Movements
    path('supply-movements/', views.supply_movement_list, name='supply_movement_list'),
    path('supply-movements/new/', views.supply_movement_create, name='supply_movement_create'),

    # Target Goals
    path('goals/', views.goal_list, name='goal_list'),
    path('goals/new/', views.goal_create, name='goal_create'),
    path('goals/<int:pk>/edit/', views.goal_edit, name='goal_edit'),
    path('goals/<int:pk>/delete/', views.goal_delete, name='goal_delete'),

    # Dictionary
    path('dictionary/', views.dictionary_view, name='dictionary'),

    # ── CSV Imports ───────────────────────────────────────────────────────
    # Catalog Items
    path('import/catalog/', import_views.catalog_import, name='catalog_import'),
    path('import/catalog/template/', import_views.catalog_import_template, name='catalog_import_template'),
    # Expenses
    path('import/expenses/', import_views.expense_import, name='expense_import'),
    path('import/expenses/template/', import_views.expense_import_template, name='expense_import_template'),
    # Sales Orders
    path('import/sales-orders/', import_views.sales_order_import, name='sales_order_import'),
    path('import/sales-orders/template/', import_views.sales_order_import_template, name='sales_order_import_template'),
    # Supply Items
    path('import/supplies/', import_views.supply_import, name='supply_import'),
    path('import/supplies/template/', import_views.supply_import_template, name='supply_import_template'),
    # Procurement / Stock-In
    path('import/procurement/', import_views.procurement_import, name='procurement_import'),
    path('import/procurement/template/', import_views.procurement_import_template, name='procurement_import_template'),
]
