from django.urls import path
from sales import views

urlpatterns = [
    path('orders/', views.sales_order_list_view, name='sales_order_list'),
    path('orders/create/', views.sales_order_create_view, name='sales_order_create'),
    path('orders/<int:pk>/', views.sales_order_detail_view, name='sales_order_detail'),
    path('orders/<int:pk>/edit/', views.sales_order_edit_view, name='sales_order_edit'),
    path('orders/<int:pk>/delete/', views.sales_order_delete_view, name='sales_order_delete'),
    path('orders/<int:pk>/approve/', views.sales_order_approve_view, name='sales_order_approve'),
    path('orders/<int:pk>/cancel/', views.sales_order_cancel_view, name='sales_order_cancel'),
    path('orders/<int:pk>/print/', views.sales_order_print_view, name='sales_order_print'),
    path('deliveries/', views.delivery_list_view, name='delivery_list'),
    path('deliveries/create/', views.delivery_create_view, name='delivery_create'),
    path('deliveries/<int:pk>/', views.delivery_detail_view, name='delivery_detail'),
    path('deliveries/<int:pk>/edit/', views.delivery_edit_view, name='delivery_edit'),
    path('deliveries/<int:pk>/delete/', views.delivery_delete_view, name='delivery_delete'),
    path('deliveries/<int:pk>/post/', views.delivery_post_view, name='delivery_post'),
    path('deliveries/<int:pk>/cancel/', views.delivery_cancel_view, name='delivery_cancel'),
    path('deliveries/<int:pk>/print/', views.delivery_print_view, name='delivery_print'),
    # Sales Returns
    path('returns/', views.sales_return_list_view, name='sales_return_list'),
    path('returns/create/', views.sales_return_create_view, name='sales_return_create'),
    path('returns/<int:pk>/', views.sales_return_detail_view, name='sales_return_detail'),
    path('returns/<int:pk>/post/', views.sales_return_post_view, name='sales_return_post'),
    path('returns/<int:pk>/cancel/', views.sales_return_cancel_view, name='sales_return_cancel'),
    path('returns/<int:pk>/delete/', views.sales_return_delete_view, name='sales_return_delete'),
]
