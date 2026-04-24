from django.urls import path
from cashflow import views
from cashflow import monthly_views
from cashflow import views_financial

app_name = 'cashflow'

urlpatterns = [
    # Transactions
    path('', views.transaction_list, name='cashflow_list'),
    path('new/', views.transaction_create, name='cashflow_create'),
    path('sync/', views.sync_cashflow, name='cashflow_sync'),
    path('<int:pk>/', views.transaction_detail, name='cashflow_detail'),
    path('<int:pk>/edit/', views.transaction_edit, name='cashflow_edit'),
    path('<int:pk>/delete/', views.transaction_delete, name='cashflow_delete'),

    # Approval workflow
    path('<int:pk>/approve/', views.transaction_approve, name='cashflow_approve'),
    path('<int:pk>/reject/', views.transaction_reject, name='cashflow_reject'),
    path('<int:pk>/cancel/', views.transaction_cancel, name='cashflow_cancel'),

    # Logs
    path('logs/', views.log_list, name='cashflow_log_list'),
    
    # Monthly Cashflow
    path('monthly/', monthly_views.monthly_dashboard, name='monthly_dashboard'),
    path('monthly/<int:year>/<int:month>/', monthly_views.monthly_detail, name='monthly_detail'),
    path('monthly/<int:year>/<int:month>/recalculate/', monthly_views.recalculate_month, name='recalculate_month'),
    path('monthly/recalculate-all/', monthly_views.recalculate_all, name='recalculate_all'),
    path('monthly/api/<int:year>/chart-data/', monthly_views.monthly_chart_data, name='monthly_chart_data'),
    path('monthly/api/<int:year>/<int:month>/auto-create/', monthly_views.auto_create_summary, name='auto_create_summary'),
    
    # New Financial Dashboard
    path('financial/', views_financial.financial_dashboard, name='financial_dashboard'),
    path('financial/cash-flow/<int:year>/<int:month>/', views_financial.cash_flow_statement, name='cash_flow_statement'),
    path('financial/profit-loss/<int:year>/<int:month>/', views_financial.profit_loss_statement, name='profit_loss_statement'),
    path('financial/balance-sheet/<int:year>/<int:month>/', views_financial.balance_sheet, name='balance_sheet'),
    path('api/financial-metrics/', views_financial.financial_metrics_api, name='financial_metrics_api'),
]
