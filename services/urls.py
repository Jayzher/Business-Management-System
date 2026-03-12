from django.urls import path
from services import views

urlpatterns = [
    path('', views.service_list, name='service_list'),
    path('create/', views.service_create, name='service_create'),
    path('<int:pk>/', views.service_detail, name='service_detail'),
    path('<int:pk>/edit/', views.service_edit, name='service_edit'),
    path('<int:pk>/delete/', views.service_delete, name='service_delete'),
    path('<int:pk>/start/', views.service_start, name='service_start'),
    path('<int:pk>/complete/', views.service_complete, name='service_complete'),
    path('<int:pk>/cancel/', views.service_cancel, name='service_cancel'),
]
