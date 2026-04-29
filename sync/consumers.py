"""
sync/consumers.py — WebSocket consumers for real-time data sync.

Provides two consumers:
  1. SyncConsumer  — authenticated WebSocket for real-time table-change
     notifications.  Both web (session auth) and mobile (JWT auth) clients
     connect here.  When a model save/delete fires, the signal layer
     broadcasts to the 'sync' channel group and every connected client
     receives {"type": "table_changed", "tables": [...]}.

  2. Clients can also subscribe to specific tables by sending:
       {"action": "subscribe", "tables": ["catalog_item", "inventory_stockbalance"]}
     and will then only receive events for those tables.
     Send {"action": "subscribe", "tables": ["*"]} to receive all events (default).
"""

import json
import logging

from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from urllib.parse import parse_qs

logger = logging.getLogger(__name__)

# Group name used by the signal broadcaster
SYNC_GROUP = 'sync'


class SyncConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket endpoint: ws(s)://<host>/ws/sync/

    Authentication:
      - Web clients: Django session cookie (handled by SessionMiddleware in ASGI)
      - Mobile clients: pass JWT token as query param ?token=<access_token>

    Protocol (JSON):
      Server → Client:
        {"type": "table_changed", "tables": ["catalog_item", ...]}
        {"type": "connected", "message": "..."}

      Client → Server:
        {"action": "subscribe", "tables": ["catalog_item"]}  — filter events
        {"action": "subscribe", "tables": ["*"]}              — receive all (default)
        {"action": "ping"}                                    — keepalive
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # None or set of table names; None means "all tables"
        self.subscribed_tables = None

    async def connect(self):
        user = self.scope.get('user')

        # If no session user, try JWT from query string
        if user is None or user.is_anonymous:
            user = await self._authenticate_jwt()

        if user is None or user.is_anonymous:
            logger.debug('WS rejected: unauthenticated')
            await self.close(code=4001)
            return

        self.scope['user'] = user
        await self.channel_layer.group_add(SYNC_GROUP, self.channel_name)
        await self.accept()
        await self.send_json({
            'type': 'connected',
            'message': f'Connected as {user.username}',
        })
        logger.debug('WS connected: user=%s channel=%s', user.username, self.channel_name)

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(SYNC_GROUP, self.channel_name)
        logger.debug('WS disconnected: channel=%s code=%s', self.channel_name, close_code)

    async def receive_json(self, content, **kwargs):
        action = content.get('action', '')

        if action == 'subscribe':
            tables = content.get('tables', ['*'])
            if tables == ['*'] or '*' in tables:
                self.subscribed_tables = None  # all
            else:
                self.subscribed_tables = set(tables)
            await self.send_json({
                'type': 'subscribed',
                'tables': list(self.subscribed_tables) if self.subscribed_tables else ['*'],
            })

        elif action == 'ping':
            await self.send_json({'type': 'pong'})

    # ── Group message handler ──────────────────────────────────────────
    async def table_changed(self, event):
        """
        Called when the channel layer receives a message with
        type='table_changed' on the SYNC_GROUP.
        """
        tables = event.get('tables', [])

        # Filter by subscription
        if self.subscribed_tables is not None:
            tables = [t for t in tables if t in self.subscribed_tables]
            if not tables:
                return

        await self.send_json({
            'type': 'table_changed',
            'tables': tables,
        })

    # ── JWT authentication helper ──────────────────────────────────────
    async def _authenticate_jwt(self):
        """Extract and validate a JWT access token from the query string."""
        query_string = self.scope.get('query_string', b'').decode('utf-8')
        params = parse_qs(query_string)
        token = params.get('token', [None])[0]
        if not token:
            return None
        return await self._validate_token(token)

    @database_sync_to_async
    def _validate_token(self, raw_token):
        try:
            from rest_framework_simplejwt.tokens import AccessToken
            from django.contrib.auth import get_user_model
            User = get_user_model()
            validated = AccessToken(raw_token)
            user_id = validated.get('user_id')
            return User.objects.get(pk=user_id)
        except Exception as exc:
            logger.debug('JWT validation failed: %s', exc)
            return None
