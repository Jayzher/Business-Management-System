"""
WSGI config for Mobile API service.
Uses mobile_settings which is API-only (no web templates).
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'inventory_system.mobile_settings')

application = get_wsgi_application()
