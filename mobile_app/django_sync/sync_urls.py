# Django Sync API URLs
# Add these to your main urls.py or create a dedicated sync app

from django.urls import path
from . import sync_views

app_name = 'sync'

urlpatterns = [
    path('pull/', sync_views.sync_pull, name='sync-pull'),
    path('push/', sync_views.sync_push, name='sync-push'),
]
