# Django Sync Integration Guide
# ================================
# 
# 1. Copy sync_views.py and sync_urls.py into your Django project
#    (either as a new 'sync' app or add to an existing app)
#
# 2. Add to your main inventory_system/urls.py:
#    
#    from django.urls import path, include
#    urlpatterns = [
#        ...
#        path('api/sync/', include('sync.urls')),  # or wherever you place it
#    ]
#
# 3. Ensure JWT auth is configured in settings.py:
#
#    REST_FRAMEWORK = {
#        'DEFAULT_AUTHENTICATION_CLASSES': [
#            'rest_framework_simplejwt.authentication.JWTAuthentication',
#        ],
#    }
#
# 4. Add token endpoints to urls.py (if not already):
#
#    from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
#    urlpatterns = [
#        ...
#        path('api/accounts/token/', TokenObtainPairView.as_view()),
#        path('api/accounts/token/refresh/', TokenRefreshView.as_view()),
#    ]
#
# 5. Add CORS headers for mobile access in settings.py:
#
#    CORS_ALLOW_ALL_ORIGINS = True  # For development only
#    # In production, specify your mobile app's origin
