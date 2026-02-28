from django.urls import path
from warehouses import views

urlpatterns = [
    path('', views.warehouse_list_view, name='warehouse_list'),
    path('locations/', views.location_list_view, name='location_list'),
    path('create/', views.warehouse_create_view, name='warehouse_create'),
    path('<int:pk>/', views.warehouse_detail_view, name='warehouse_detail'),
    path('<int:pk>/edit/', views.warehouse_edit_view, name='warehouse_edit'),
    path('<int:pk>/delete/', views.warehouse_delete_view, name='warehouse_delete'),
    path('locations/create/', views.location_create_view, name='location_create'),
    path('locations/<int:pk>/edit/', views.location_edit_view, name='location_edit'),
    path('locations/<int:pk>/delete/', views.location_delete_view, name='location_delete'),
]
