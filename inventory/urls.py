from django.urls import path
from inventory import views

urlpatterns = [
    path('inventory/', views.item_inventory_view, name='item_inventory'),
    path('moves/', views.stock_move_list_view, name='stock_move_list'),
    path('transfers/', views.transfer_list_view, name='transfer_list'),
    path('transfers/create/', views.transfer_create_view, name='transfer_create'),
    path('transfers/<int:pk>/', views.transfer_detail_view, name='transfer_detail'),
    path('transfers/<int:pk>/edit/', views.transfer_edit_view, name='transfer_edit'),
    path('transfers/<int:pk>/delete/', views.transfer_delete_view, name='transfer_delete'),
    path('transfers/<int:pk>/post/', views.transfer_post_view, name='transfer_post'),
    path('transfers/<int:pk>/cancel/', views.transfer_cancel_view, name='transfer_cancel'),
    path('adjustments/', views.adjustment_list_view, name='adjustment_list'),
    path('adjustments/create/', views.adjustment_create_view, name='adjustment_create'),
    path('adjustments/<int:pk>/', views.adjustment_detail_view, name='adjustment_detail'),
    path('adjustments/<int:pk>/edit/', views.adjustment_edit_view, name='adjustment_edit'),
    path('adjustments/<int:pk>/delete/', views.adjustment_delete_view, name='adjustment_delete'),
    path('adjustments/<int:pk>/approve/', views.adjustment_approve_view, name='adjustment_approve'),
    path('adjustments/<int:pk>/post/', views.adjustment_post_view, name='adjustment_post'),
    path('adjustments/<int:pk>/cancel/', views.adjustment_cancel_view, name='adjustment_cancel'),
    path('damaged/', views.damaged_list_view, name='damaged_list'),
    path('damaged/create/', views.damaged_create_view, name='damaged_create'),
    path('damaged/<int:pk>/', views.damaged_detail_view, name='damaged_detail'),
    path('damaged/<int:pk>/edit/', views.damaged_edit_view, name='damaged_edit'),
    path('damaged/<int:pk>/delete/', views.damaged_delete_view, name='damaged_delete'),
    path('damaged/<int:pk>/post/', views.damaged_post_view, name='damaged_post'),
    path('damaged/<int:pk>/cancel/', views.damaged_cancel_view, name='damaged_cancel'),
]
