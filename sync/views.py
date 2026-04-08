import time
import logging

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
    return timezone.datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


def _get_changes(model_class, serializer_class, since_dt, extra_filter=None):
    """
    Return {created: [...], updated: [...], deleted: [...]} for a model
    since the given datetime.
    """
    qs = model_class.objects.all()
    if extra_filter:
        qs = qs.filter(extra_filter)

    if since_dt:
        created = qs.filter(created_at__gt=since_dt)
        updated = qs.filter(updated_at__gt=since_dt).exclude(created_at__gt=since_dt)
    else:
        created = qs
        updated = model_class.objects.none()

    deleted = []
    if hasattr(model_class, 'all_objects'):
        deleted_qs = model_class.all_objects.filter(is_active=False)
        if since_dt:
            deleted_qs = deleted_qs.filter(updated_at__gt=since_dt)
        deleted = list(deleted_qs.values_list('id', flat=True))

    return {
        'created': serializer_class(created, many=True).data,
        'updated': serializer_class(updated, many=True).data,
        'deleted': deleted,
    }


def _get_simple_changes(model_class, serializer_class, since_dt):
    """For models without created_at — just return all or changed since."""
    qs = model_class.objects.all()

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
        deleted_qs = model_class.all_objects.filter(is_active=False)
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
        user_perms = WarehousePermission.objects.filter(user=request.user)
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
