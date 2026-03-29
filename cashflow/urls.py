from django.urls import path
from cashflow import views

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
]
