from django.urls import path
from catalog import views

urlpatterns = [
    path('items/', views.item_list_view, name='item_list'),
    path('items/export-excel/', views.catalog_export_excel_view, name='catalog_export_excel'),
    path('items/print/', views.catalog_print_view, name='catalog_print'),
    path('items/create/', views.item_create_view, name='item_create'),
    path('items/<int:pk>/', views.item_detail_view, name='item_detail'),
    path('items/<int:pk>/edit/', views.item_edit_view, name='item_edit'),
    path('items/<int:pk>/delete/', views.item_delete_view, name='item_delete'),
    path('categories/', views.category_list_view, name='category_list'),
    path('categories/create/', views.category_create_view, name='category_create'),
    path('categories/<int:pk>/edit/', views.category_edit_view, name='category_edit'),
    path('categories/<int:pk>/delete/', views.category_delete_view, name='category_delete'),
    path('units/', views.unit_list_view, name='unit_list'),
    path('units/create/', views.unit_create_view, name='unit_create'),
    path('units/<int:pk>/edit/', views.unit_edit_view, name='unit_edit'),
    path('units/<int:pk>/delete/', views.unit_delete_view, name='unit_delete'),
    path('unit-conversions/', views.unit_conversion_list_view, name='unit_conversion_list'),
    path('unit-conversions/create/', views.unit_conversion_create_view, name='unit_conversion_create'),
    path('unit-conversions/<int:pk>/edit/', views.unit_conversion_edit_view, name='unit_conversion_edit'),
    path('unit-conversions/<int:pk>/delete/', views.unit_conversion_delete_view, name='unit_conversion_delete'),
]
