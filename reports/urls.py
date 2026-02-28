from django.urls import path
from reports import views

urlpatterns = [
    path('', views.reports_dashboard_view, name='reports_dashboard'),
    path('stock-on-hand/', views.stock_on_hand_view, name='report_stock_on_hand'),
    path('stock-movement/', views.stock_movement_view, name='report_stock_movement'),
    path('low-stock/', views.low_stock_view, name='report_low_stock'),
    path('profit-margin/', views.profit_margin_view, name='report_profit_margin'),
    path('inventory-valuation/', views.inventory_valuation_view, name='report_inventory_valuation'),
    path('sales/', views.sales_report_view, name='report_sales'),
    path('expenses/', views.expense_report_view, name='report_expenses'),
    path('financial-statement/', views.financial_statement_view, name='report_financial_statement'),
    path('stock-aging/', views.stock_aging_view, name='report_stock_aging'),
]
