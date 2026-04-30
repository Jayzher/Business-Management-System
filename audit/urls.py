from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views, api_views

app_name = 'audit'

# DRF API router
router = DefaultRouter()
router.register(r'system-logs', api_views.AuditLogViewSet, basename='api-system-log')
router.register(r'manual-logs', api_views.ManualLogViewSet, basename='api-manual-log')

urlpatterns = [
    # Template views (server-rendered pages)
    path('system/', views.system_logs, name='system_logs'),
    path('manual/', views.manual_logs, name='manual_logs'),
    path('manual/create/', views.manual_log_create, name='manual_log_create'),
    path('manual/<int:pk>/', views.manual_log_detail, name='manual_log_detail'),

    # DRF API endpoints (JSON, paginated, filtered)
    path('api/', include(router.urls)),
]
