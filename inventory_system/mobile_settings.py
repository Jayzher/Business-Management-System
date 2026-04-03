"""
Mobile API settings — lightweight, API-only Django config.
Shares the same models/DB (Neon PostgreSQL) as the web version
but strips out templates, admin UI, and web-only middleware.
"""

from inventory_system.settings import *  # noqa: F401,F403

# Override the root URL conf to the mobile API-only routes
ROOT_URLCONF = 'inventory_system.mobile_urls'

# Override WSGI
WSGI_APPLICATION = 'inventory_system.mobile_wsgi.application'

# Strip down to API-only middleware (no CSRF, no template middleware)
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
]

# JWT-only auth for mobile (no session auth needed)
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 50,
}

# Longer token lifetimes for mobile
from datetime import timedelta  # noqa: E402

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=6),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=30),
    'ROTATE_REFRESH_TOKENS': True,
}

# CORS — mobile apps don't have a fixed origin
CORS_ALLOW_ALL_ORIGINS = True
