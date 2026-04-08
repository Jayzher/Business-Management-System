"""
ASGI config for inventory_system project.

Real-time sync events are delivered via Pusher Channels (hosted, free tier)
so no in-process WebSocket server is needed here.
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'inventory_system.settings')

application = get_asgi_application()
