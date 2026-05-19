import time
import logging
from datetime import datetime, timezone as dt_timezone

from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.models import User, Role, WarehousePermission
from accounts.serializers import UserSerializer, RoleSerializer, WarehousePermissionSerializer
from catalog.models import Category, Unit, UnitConversion, Item
from catalog.serializers import CategorySerializer, UnitSerializer, UnitConversionSerializer, ItemSerializer
from inventory.models import StockBalance
from inventory.serializers import StockBalanceSerializer
from partners.models import Supplier, Customer
from partners.serializers import SupplierSerializer, CustomerSerializer
from pos.models import POSRegister, POSSale, POSSaleLine, POSPayment, POSShift, SaleStatus
from pos.serializers import POSRegisterSerializer
from pricing.models import PriceList, PriceListItem, DiscountRule
from pricing.serializers import PriceListSerializer, PriceListItemSerializer, DiscountRuleSerializer
from warehouses.models import Warehouse, Location
from warehouses.serializers import WarehouseSerializer, LocationSerializer

logger = logging.getLogger(__name__)


def _ms_to_dt(ms):
    """Convert milliseconds timestamp to datetime, or return None."""
    if ms is None:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=dt_timezone.utc)


def _get_changes(model_class, serializer_class, since_dt, extra_filter=None):
    """
    Return {created: [...], updated: [...], deleted: [...]} for a model
    since the given datetime.
    
    Reads from 'default' (Neon) to ensure mobile clients get authoritative data.
    """
    qs = model_class.objects.using('default').all()
    if extra_filter:
        qs = qs.filter(extra_filter)

    if since_dt:
        created = qs.filter(created_at__gt=since_dt)
        updated = qs.filter(updated_at__gt=since_dt).exclude(created_at__gt=since_dt)
    else:
        created = qs
        updated = model_class.objects.using('default').none()

    deleted = []
    if hasattr(model_class, 'all_objects'):
        deleted_qs = model_class.all_objects.using('default').filter(is_active=False)
        if since_dt:
            deleted_qs = deleted_qs.filter(updated_at__gt=since_dt)
        deleted = list(deleted_qs.values_list('id', flat=True))

    return {
        'created': serializer_class(created, many=True).data,
        'updated': serializer_class(updated, many=True).data,
        'deleted': deleted,
    }


def _get_simple_changes(model_class, serializer_class, since_dt):
    """For models without created_at — just return all or changed since.
    
    Reads from 'default' (Neon) to ensure mobile clients get authoritative data.
    """
    qs = model_class.objects.using('default').all()

    if since_dt and hasattr(model_class, 'updated_at'):
        changed = qs.filter(updated_at__gt=since_dt)
        result = {
            'created': [],
            'updated': serializer_class(changed, many=True).data,
            'deleted': [],
        }
    else:
        result = {
            'created': serializer_class(qs, many=True).data,
            'updated': [],
            'deleted': [],
        }

    # Surface soft-deleted IDs so mobile can remove them locally.
    if hasattr(model_class, 'all_objects'):
        deleted_qs = model_class.all_objects.using('default').filter(is_active=False)
        if since_dt:
            deleted_qs = deleted_qs.filter(updated_at__gt=since_dt)
        result['deleted'] = list(deleted_qs.values_list('id', flat=True))

    return result


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def sync_pull(request):
    """
    Pull changes from server since last_pulled_at.
    Client sends: { "last_pulled_at": <ms timestamp or null>, "tables": [...] }
    Server returns: { "changes": {...}, "timestamp": <ms> }
    """
    last_pulled_at_ms = request.data.get('last_pulled_at')
    since_dt = _ms_to_dt(last_pulled_at_ms)
    requested_tables = request.data.get('tables', [])
    now_ms = int(time.time() * 1000)

    changes = {}

    table_handlers = {
        'categories': lambda: _get_simple_changes(Category, CategorySerializer, since_dt),
        'units': lambda: _get_simple_changes(Unit, UnitSerializer, since_dt),
        'unit_conversions': lambda: _get_simple_changes(UnitConversion, UnitConversionSerializer, since_dt),
        'items': lambda: _get_simple_changes(Item, ItemSerializer, since_dt),
        'warehouses': lambda: _get_simple_changes(Warehouse, WarehouseSerializer, since_dt),
        'locations': lambda: _get_simple_changes(Location, LocationSerializer, since_dt),
        'suppliers': lambda: _get_simple_changes(Supplier, SupplierSerializer, since_dt),
        'customers': lambda: _get_simple_changes(Customer, CustomerSerializer, since_dt),
        'stock_balances': lambda: _get_simple_changes(StockBalance, StockBalanceSerializer, since_dt),
        'pos_registers': lambda: _get_simple_changes(POSRegister, POSRegisterSerializer, since_dt),
        'price_lists': lambda: _get_simple_changes(PriceList, PriceListSerializer, since_dt),
        'price_list_items': lambda: _get_simple_changes(PriceListItem, PriceListItemSerializer, since_dt),
        'discount_rules': lambda: _get_simple_changes(DiscountRule, DiscountRuleSerializer, since_dt),
        'users': lambda: _get_simple_changes(User, UserSerializer, since_dt),
        'roles': lambda: _get_simple_changes(Role, RoleSerializer, since_dt),
    }

    for table in requested_tables:
        if table in table_handlers:
            changes[table] = table_handlers[table]()

    # Special case: warehouse_permissions (user-scoped)
    if 'warehouse_permissions' in requested_tables:
        user_perms = WarehousePermission.objects.using('default').filter(user=request.user)
        changes['warehouse_permissions'] = {
            'created': WarehousePermissionSerializer(user_perms, many=True).data,
            'updated': [],
            'deleted': [],
        }

    return Response({
        'changes': changes,
        'timestamp': now_ms,
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def sync_push(request):
    """
    Push local changes from mobile to server.
    Client sends: { "changes": { "table_name": [{ operation, data }] } }
    Server returns: { "synced_ids": [...], "id_mappings": { "table": [{ local_id, server_id }] } }
    """
    changes = request.data.get('changes', {})
    synced_ids = []
    id_mappings = {}

    # ─── POS Sales ───
    if 'pos_sales' in changes:
        id_mappings['pos_sales'] = []
        for item in changes['pos_sales']:
            queue_id = item.get('id')
            op = item.get('operation', 'CREATE')
            data = item.get('data', {})

            if op == 'CREATE':
                try:
                    with transaction.atomic():
                        from pos.services.checkout import generate_sale_number, sync_pos_sale_stock_moves

                        # Resolve register from the shift (register is required on POSSale)
                        shift_id = data.get('shift')
                        shift = POSShift.objects.select_related('register').get(pk=shift_id)

                        # Accept both old mobile field names and canonical model names
                        sale = POSSale.objects.create(
                            sale_no=generate_sale_number(),
                            register=shift.register,
                            shift=shift,
                            warehouse_id=data['warehouse'],
                            location_id=(
                                data.get('location')
                                or shift.register.default_location_id
                            ),
                            customer_id=data.get('customer'),
                            subtotal=data.get('subtotal', 0),
                            discount_total=(
                                data.get('discount_total')
                                or data.get('discount_amount', 0)
                            ),
                            tax_total=(
                                data.get('tax_total')
                                or data.get('tax_amount', 0)
                            ),
                            grand_total=(
                                data.get('grand_total')
                                or data.get('total', 0)
                            ),
                            notes=data.get('notes', ''),
                            created_by=request.user,
                            status=SaleStatus.PAID,
                        )

                        for line_data in data.get('lines', []):
                            POSSaleLine.objects.create(
                                sale=sale,
                                item_id=line_data['item_id'],
                                unit_id=line_data['unit_id'],
                                location_id=line_data.get('location_id'),
                                qty=line_data['qty'],
                                unit_price=line_data['unit_price'],
                                discount_amount=line_data.get('discount_amount', 0),
                                line_total=line_data['line_total'],
                            )

                        for payment_data in data.get('payments', []):
                            POSPayment.objects.create(
                                sale=sale,
                                method=payment_data['method'],
                                amount=payment_data['amount'],
                                reference_no=(
                                    payment_data.get('reference_no')
                                    or payment_data.get('reference', '')
                                ),
                            )

                        # Idempotent stock deduction designed for sync scenarios
                        sync_pos_sale_stock_moves(sale.pk, request.user)

                    id_mappings['pos_sales'].append({
                        'local_id': data.get('local_id'),
                        'server_id': sale.id,
                    })
                    if queue_id:
                        synced_ids.append(queue_id)
                except Exception as e:
                    logger.error(f'Sync push error (pos_sales CREATE): {e}')

    # ─── POS Shifts ───
    if 'pos_shifts' in changes:
        id_mappings['pos_shifts'] = []
        for item in changes['pos_shifts']:
            queue_id = item.get('id')
            op = item.get('operation', 'CREATE')
            data = item.get('data', {})

            try:
                if op == 'CREATE':
                    from pos.services.checkout import open_shift
                    register = POSRegister.objects.get(pk=data['register'])
                    opening_cash = (
                        data.get('opening_cash')
                        or data.get('opening_balance', 0)
                    )
                    shift = open_shift(register, request.user, opening_cash)
                    id_mappings['pos_shifts'].append({
                        'local_id': data.get('local_id'),
                        'server_id': shift.id,
                    })
                elif op == 'UPDATE':
                    server_id = data.get('server_id')
                    if server_id:
                        from pos.services.checkout import close_shift
                        shift = POSShift.objects.get(pk=server_id)
                        closing_cash = (
                            data.get('closing_cash_declared')
                            or data.get('closing_balance', 0)
                        )
                        close_shift(shift, request.user, closing_cash)
                if queue_id:
                    synced_ids.append(queue_id)
            except Exception as e:
                logger.error(f'Sync push error (pos_shifts {op}): {e}')

    # ─── Cashflow Transactions ───
    if 'cashflow_transactions' in changes:
        id_mappings['cashflow_transactions'] = []
        for item in changes['cashflow_transactions']:
            queue_id = item.get('id')
            op = item.get('operation', 'CREATE')
            data = item.get('data', {})

            try:
                if op == 'CREATE':
                    from cashflow.models import CashFlowTransaction, CashFlowStatus
                    txn = CashFlowTransaction.objects.create(
                        transaction_number=CashFlowTransaction.generate_next_number(),
                        category=data['category'],
                        flow_type=data['flow_type'],
                        amount=data['amount'],
                        transaction_date=(
                            data.get('transaction_date')
                            or timezone.now().date()
                        ),
                        payment_method=data.get('payment_method', 'CASH'),
                        reference_no=data.get('reference_no', ''),
                        reason=data.get('reason', ''),
                        notes=(
                            data.get('notes')
                            or data.get('description', '')
                        ),
                        status=CashFlowStatus.PENDING,
                        created_by=request.user,
                    )
                    id_mappings['cashflow_transactions'].append({
                        'local_id': data.get('local_id'),
                        'server_id': txn.id,
                    })
                if queue_id:
                    synced_ids.append(queue_id)
            except Exception as e:
                logger.error(f'Sync push error (cashflow {op}): {e}')

    # ─── Stock Moves (manual adjustments from mobile) ───
    if 'stock_moves' in changes:
        id_mappings['stock_moves'] = []
        for item in changes['stock_moves']:
            queue_id = item.get('id')
            op = item.get('operation', 'CREATE')
            data = item.get('data', {})

            try:
                if op == 'CREATE':
                    from inventory.models import StockMove, MoveType, MoveStatus
                    # Mobile sends 'location' for outbound moves; map to from_location
                    move_type = data.get('move_type', MoveType.ADJUST)
                    is_inbound = move_type in (
                        MoveType.RECEIVE, MoveType.RETURN_IN,
                    )
                    move = StockMove.objects.create(
                        item_id=data['item'],
                        from_location_id=None if is_inbound else data.get('location'),
                        to_location_id=data.get('location') if is_inbound else None,
                        move_type=move_type,
                        qty=data['qty'],
                        unit_id=data.get('unit'),
                        reference_number=data.get('reference_number') or data.get('reference', ''),
                        reference_type=data.get('reference_type', 'Mobile'),
                        notes=data.get('notes', ''),
                        status=MoveStatus.POSTED,
                        created_by=request.user,
                        posted_by=request.user,
                        posted_at=timezone.now(),
                    )
                    id_mappings['stock_moves'].append({
                        'local_id': data.get('local_id'),
                        'server_id': move.id,
                    })
                if queue_id:
                    synced_ids.append(queue_id)
            except Exception as e:
                logger.error(f'Sync push error (stock_moves {op}): {e}')

    # ─── Sales Orders ───
    if 'sales_orders' in changes:
        id_mappings['sales_orders'] = []
        for item in changes['sales_orders']:
            queue_id = item.get('id')
            op = item.get('operation', 'CREATE')
            data = item.get('data', {})

            try:
                if op == 'CREATE':
                    from sales.models import SalesOrder, SalesOrderLine
                    with transaction.atomic():
                        order = SalesOrder.objects.create(
                            customer_id=data.get('customer'),
                            warehouse_id=data['warehouse'],
                            order_date=data.get('order_date', timezone.now().date()),
                            subtotal=data.get('subtotal', 0),
                            discount_amount=data.get('discount_amount', 0),
                            tax_amount=data.get('tax_amount', 0),
                            total=data.get('total', 0),
                            notes=data.get('notes', ''),
                            created_by=request.user,
                            status=data.get('status', 'DRAFT'),
                        )
                        for line_data in data.get('lines', []):
                            SalesOrderLine.objects.create(
                                order=order,
                                item_id=line_data['item_id'],
                                unit_id=line_data.get('unit_id'),
                                qty=line_data['qty'],
                                unit_price=line_data['unit_price'],
                                discount_amount=line_data.get('discount_amount', 0),
                                line_total=line_data['line_total'],
                            )
                    id_mappings['sales_orders'].append({
                        'local_id': data.get('local_id'),
                        'server_id': order.id,
                    })
                if queue_id:
                    synced_ids.append(queue_id)
            except Exception as e:
                logger.error(f'Sync push error (sales_orders {op}): {e}')

    return Response({
        'synced_ids': synced_ids,
        'id_mappings': id_mappings,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def ws_info(request):
    """
    Return WebSocket connection details for mobile clients.

    Mobile clients call this endpoint with their JWT token to get the
    WebSocket URL they should connect to.  The JWT access token is passed
    as a query parameter on the WS URL for authentication.

    Response:
      {
        "ws_url": "wss://example.com/ws/sync/?token=<access_token>",
        "protocol": "json",
        "events": ["table_changed"],
        "actions": ["subscribe", "ping"]
      }
    """
    # Extract the access token from the Authorization header
    auth_header = request.META.get('HTTP_AUTHORIZATION', '')
    token = ''
    if auth_header.startswith('Bearer '):
        token = auth_header[7:]

    # Build the WebSocket URL
    scheme = 'wss' if request.is_secure() else 'ws'
    host = request.get_host()
    ws_url = f'{scheme}://{host}/ws/sync/'
    if token:
        ws_url += f'?token={token}'

    return Response({
        'ws_url': ws_url,
        'protocol': 'json',
        'events': [
            'table_changed',   # lightweight: {"tables": [...]}
            'data_changed',    # rich: {"table": "...", "action": "upsert|delete", "rows": [...]}
            'connected',
            'subscribed',
            'pong',
        ],
        'actions': ['subscribe', 'ping'],
        'subscribe_example': {
            'action': 'subscribe',
            'tables': ['catalog_item', 'inventory_stockbalance'],
        },
    })


# ── Catch-up endpoint for web clients ──────────────────────────────────
# When the WS reconnects after being offline, the client calls this to
# discover which tables changed while it was disconnected.

from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_GET


@require_GET
@login_required
def sync_catchup(request):
    """
    Lightweight catch-up check for web clients after WS reconnection.

    Query params:
      since_ms — millisecond timestamp of the last event the client received.
                 If omitted, returns has_changes=True (force refresh).

    Response:
      {
        "has_changes": true/false,
        "changed_tables": ["catalog_item", "inventory_stockbalance", ...],
        "server_time_ms": 1715000000000,
        "outbox_pending": 0
      }

    The client uses this to decide whether to refresh the page content.
    This is much cheaper than a full sync_pull — it just checks updated_at
    timestamps across the synced models.
    """
    since_ms = request.GET.get('since_ms')
    now_ms = int(time.time() * 1000)

    # If no timestamp provided, assume everything is stale
    if not since_ms:
        return JsonResponse({
            'has_changes': True,
            'changed_tables': ['*'],
            'server_time_ms': now_ms,
            'outbox_pending': _get_outbox_pending(),
        })

    try:
        since_dt = datetime.fromtimestamp(
            int(since_ms) / 1000, tz=dt_timezone.utc
        )
    except (ValueError, TypeError, OSError):
        return JsonResponse({
            'has_changes': True,
            'changed_tables': ['*'],
            'server_time_ms': now_ms,
            'outbox_pending': _get_outbox_pending(),
        })

    # Check each synced model for rows updated after since_dt.
    # We only need to know IF there are changes, not what they are.
    changed_tables = []

    _CATCHUP_MODELS = _get_catchup_models()

    for db_table, model in _CATCHUP_MODELS:
        try:
            if hasattr(model, 'updated_at'):
                if model.objects.using('default').filter(updated_at__gt=since_dt).exists():
                    changed_tables.append(db_table)
            elif hasattr(model, 'created_at'):
                if model.objects.using('default').filter(created_at__gt=since_dt).exists():
                    changed_tables.append(db_table)
        except Exception:
            # If a model query fails, include it as potentially changed
            changed_tables.append(db_table)

    return JsonResponse({
        'has_changes': len(changed_tables) > 0,
        'changed_tables': changed_tables,
        'server_time_ms': now_ms,
        'outbox_pending': _get_outbox_pending(),
        'last_server_sync_ms': _get_last_server_sync_ms(),
        'changelog_synced_id': _get_changelog_synced_id(),
    })


def _get_outbox_pending() -> int:
    """Return count of pending outbox entries."""
    try:
        from sync.models import SyncOutbox, SyncOutboxStatus
        return SyncOutbox.objects.using('local_cache').filter(
            status=SyncOutboxStatus.PENDING
        ).count()
    except Exception:
        return 0


def _get_catchup_models():
    """
    Return a list of (db_table, model_class) for all synced models.
    Cached after first call.
    """
    if not hasattr(_get_catchup_models, '_cache'):
        from django.apps import apps
        from sync.signals import SYNCED_APP_LABELS

        result = []
        for model in apps.get_models():
            if model._meta.app_label in SYNCED_APP_LABELS:
                result.append((model._meta.db_table, model))
        _get_catchup_models._cache = result

    return _get_catchup_models._cache


def _get_last_server_sync_ms() -> int | None:
    """Return the last time the server synced Neon → local_cache (ms timestamp)."""
    try:
        from sync.startup_sync import get_last_sync_time
        dt = get_last_sync_time()
        if dt:
            return int(dt.timestamp() * 1000)
    except Exception:
        pass
    return None


def _get_changelog_synced_id() -> int | None:
    """Return the last-synced NeonChangeLog ID from local_cache."""
    try:
        from sync.startup_sync import get_last_synced_log_id
        return get_last_synced_log_id()
    except Exception:
        return None
