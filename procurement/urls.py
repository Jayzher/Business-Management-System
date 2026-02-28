from django.urls import path
from procurement import views

urlpatterns = [
    path('purchase-orders/', views.purchase_order_list_view, name='purchase_order_list'),
    path('purchase-orders/create/', views.purchase_order_create_view, name='purchase_order_create'),
    path('purchase-orders/<int:pk>/', views.purchase_order_detail_view, name='purchase_order_detail'),
    path('purchase-orders/<int:pk>/edit/', views.purchase_order_edit_view, name='purchase_order_edit'),
    path('purchase-orders/<int:pk>/delete/', views.purchase_order_delete_view, name='purchase_order_delete'),
    path('purchase-orders/<int:pk>/approve/', views.purchase_order_approve_view, name='purchase_order_approve'),
    path('purchase-orders/<int:pk>/cancel/', views.purchase_order_cancel_view, name='purchase_order_cancel'),
    path('purchase-orders/<int:pk>/print/', views.purchase_order_print_view, name='purchase_order_print'),
    path('goods-receipts/', views.goods_receipt_list_view, name='goods_receipt_list'),
    path('goods-receipts/create/', views.goods_receipt_create_view, name='goods_receipt_create'),
    path('goods-receipts/<int:pk>/', views.goods_receipt_detail_view, name='goods_receipt_detail'),
    path('goods-receipts/<int:pk>/edit/', views.goods_receipt_edit_view, name='goods_receipt_edit'),
    path('goods-receipts/<int:pk>/delete/', views.goods_receipt_delete_view, name='goods_receipt_delete'),
    path('goods-receipts/<int:pk>/post/', views.goods_receipt_post_view, name='goods_receipt_post'),
    path('goods-receipts/<int:pk>/cancel/', views.goods_receipt_cancel_view, name='goods_receipt_cancel'),
    path('goods-receipts/<int:pk>/print/', views.goods_receipt_print_view, name='goods_receipt_print'),
    # Purchase Returns
    path('purchase-returns/', views.purchase_return_list_view, name='purchase_return_list'),
    path('purchase-returns/create/', views.purchase_return_create_view, name='purchase_return_create'),
    path('purchase-returns/<int:pk>/', views.purchase_return_detail_view, name='purchase_return_detail'),
    path('purchase-returns/<int:pk>/post/', views.purchase_return_post_view, name='purchase_return_post'),
    path('purchase-returns/<int:pk>/cancel/', views.purchase_return_cancel_view, name='purchase_return_cancel'),
    path('purchase-returns/<int:pk>/delete/', views.purchase_return_delete_view, name='purchase_return_delete'),
]
