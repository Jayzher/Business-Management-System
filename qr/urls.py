from django.urls import path
from qr import views

urlpatterns = [
    path('', views.qr_list_view, name='qr_list'),
    path('scan/', views.qr_scan_view, name='qr_scan'),
    path('print/', views.qr_print_view, name='qr_print'),
]
