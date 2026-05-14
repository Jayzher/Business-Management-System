from django.urls import path
from . import views

app_name = 'sync'

urlpatterns = [
    path('pull/', views.sync_pull, name='sync-pull'),
    path('push/', views.sync_push, name='sync-push'),
    path('ws-info/', views.ws_info, name='ws-info'),
    path('catchup/', views.sync_catchup, name='sync-catchup'),
]
