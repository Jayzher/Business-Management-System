from django.urls import path
from partners import views

urlpatterns = [
    path('suppliers/', views.supplier_list_view, name='supplier_list'),
    path('suppliers/create/', views.supplier_create_view, name='supplier_create'),
    path('suppliers/<int:pk>/edit/', views.supplier_edit_view, name='supplier_edit'),
    path('suppliers/<int:pk>/delete/', views.supplier_delete_view, name='supplier_delete'),
    path('customers/', views.customer_list_view, name='customer_list'),
    path('customers/create/', views.customer_create_view, name='customer_create'),
    path('customers/<int:pk>/edit/', views.customer_edit_view, name='customer_edit'),
    path('customers/<int:pk>/delete/', views.customer_delete_view, name='customer_delete'),
]
