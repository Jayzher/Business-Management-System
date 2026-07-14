from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum, F
from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from inventory.models import (
    StockMove, StockBalance, MoveType,
    StockAdjustment, StockAdjustmentLine,
    DamagedReport, DamagedReportLine,
    StockTransfer, StockTransferLine,
    InventoryToSupplyTransfer, InventoryToSupplyTransferLine,
)
from inventory.serializers import (
    StockMoveSerializer, StockBalanceSerializer,
    StockAdjustmentSerializer, DamagedReportSerializer,
    StockTransferSerializer,
)
from inventory.forms import (
    StockTransferForm, StockTransferLineFormSet,
    StockAdjustmentForm, StockAdjustmentLineFormSet,
    DamagedReportForm, DamagedReportLineFormSet,
    InventoryToSupplyTransferForm, InventoryToSupplyTransferLineFormSet,
)
from django.utils import timezone
from inventory.services import (
    post_transfer, post_adjustment, post_damaged_report, cancel_document,
    post_inventory_to_supply, cancel_inventory_to_supply,
    save_with_document_number,
)
from core.models import DocumentStatus
from core.utils import redirect_back
from accounts.decorators import write_denied_for_viewer, warehouse_access, adjustment_access, HasRole


# ── API Views ──────────────────────────────────────────────────────────────

class StockMoveViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = StockMove.objects.select_related(
        'item', 'unit', 'from_location', 'to_location', 'created_by'
    ).all()
    serializer_class = StockMoveSerializer
    filterset_fields = ['move_type', 'item', 'status']
    search_fields = ['item__code', 'item__name', 'reference_number']


class StockBalanceViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = StockBalance.objects.select_related(
        'item', 'location', 'location__warehouse'
    ).all()
    serializer_class = StockBalanceSerializer
    filterset_fields = ['item', 'location', 'location__warehouse']


class StockTransferViewSet(viewsets.ModelViewSet):
    queryset = StockTransfer.objects.select_related(
        'from_warehouse', 'to_warehouse', 'created_by'
    ).prefetch_related('lines').all()
    serializer_class = StockTransferSerializer
    filterset_fields = ['status', 'from_warehouse', 'to_warehouse']

    @action(detail=True, methods=['post'])
    def post_transfer(self, request, pk=None):
        transfer = self.get_object()
        try:
            transfer = post_transfer(transfer, request.user)
            return Response({'status': 'posted', 'document_number': transfer.document_number})
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class StockAdjustmentViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, HasRole]
    required_roles = ['Admin', 'Manager', 'Manager (View Only)', 'Warehouse Staff']
    queryset = StockAdjustment.objects.select_related(
        'warehouse', 'created_by'
    ).prefetch_related('lines').all()
    serializer_class = StockAdjustmentSerializer
    filterset_fields = ['status', 'warehouse']

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        adjustment = self.get_object()
        if adjustment.status != DocumentStatus.DRAFT:
            return Response({'error': 'Only DRAFT adjustments can be approved.'}, status=status.HTTP_400_BAD_REQUEST)
        from django.utils import timezone
        adjustment.status = DocumentStatus.APPROVED
        adjustment.approved_by = request.user
        adjustment.approved_at = timezone.now()
        adjustment.save(update_fields=['status', 'approved_by', 'approved_at', 'updated_at'])
        return Response({'status': 'approved'})

    @action(detail=True, methods=['post'], url_path='post')
    def post_adjustment(self, request, pk=None):
        adjustment = self.get_object()
        try:
            adjustment = post_adjustment(adjustment, request.user)
            return Response({'status': 'posted', 'document_number': adjustment.document_number})
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class DamagedReportViewSet(viewsets.ModelViewSet):
    queryset = DamagedReport.objects.select_related(
        'warehouse', 'created_by'
    ).prefetch_related('lines').all()
    serializer_class = DamagedReportSerializer
    filterset_fields = ['status', 'warehouse']

    @action(detail=True, methods=['post'], url_path='post')
    def post_report(self, request, pk=None):
        report = self.get_object()
        try:
            report = post_damaged_report(report, request.user)
            return Response({'status': 'posted', 'document_number': report.document_number})
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


# ── Template Action Views ───────────────────────────────────────────────────

@login_required
@warehouse_access
@write_denied_for_viewer
def transfer_post_view(request, pk):
    obj = get_object_or_404(StockTransfer, pk=pk)
    if request.method == 'POST':
        try:
            obj = post_transfer(obj, request.user)
            from inventory.services import format_skipped_lines_message
            warning = format_skipped_lines_message(obj)
            if warning:
                messages.warning(request, warning)
            else:
                messages.success(request, f'Transfer {obj.document_number} posted. Stock updated.')
        except ValueError as e:
            messages.error(request, str(e))
    return redirect_back(request, 'transfer_detail', pk=pk)


@login_required
@warehouse_access
@write_denied_for_viewer
def transfer_cancel_view(request, pk):
    obj = get_object_or_404(StockTransfer, pk=pk)
    if request.method == 'POST':
        try:
            cancel_document(obj, request.user)
            messages.success(request, f'Transfer {obj.document_number} cancelled.')
        except ValueError as e:
            messages.error(request, str(e))
    return redirect_back(request, 'transfer_detail', pk=pk)


@login_required
@adjustment_access
@write_denied_for_viewer
def adjustment_approve_view(request, pk):
    obj = get_object_or_404(StockAdjustment, pk=pk)
    if request.method == 'POST':
        if obj.status != DocumentStatus.DRAFT:
            messages.error(request, 'Only DRAFT adjustments can be approved.')
        else:
            obj.status = DocumentStatus.APPROVED
            obj.approved_by = request.user
            obj.approved_at = timezone.now()
            obj.save(update_fields=['status', 'approved_by', 'approved_at', 'updated_at'])
            messages.success(request, f'Adjustment {obj.document_number} approved.')
    return redirect_back(request, 'adjustment_detail', pk=pk)


@login_required
@adjustment_access
@write_denied_for_viewer
def adjustment_post_view(request, pk):
    obj = get_object_or_404(StockAdjustment, pk=pk)
    if request.method == 'POST':
        try:
            obj = post_adjustment(obj, request.user)
            from inventory.services import format_skipped_lines_message
            warning = format_skipped_lines_message(obj)
            if warning:
                messages.warning(request, warning)
            else:
                messages.success(request, f'Adjustment {obj.document_number} posted. Stock updated.')
        except ValueError as e:
            messages.error(request, str(e))
    return redirect_back(request, 'adjustment_detail', pk=pk)


@login_required
@adjustment_access
@write_denied_for_viewer
def adjustment_cancel_view(request, pk):
    obj = get_object_or_404(StockAdjustment, pk=pk)
    if request.method == 'POST':
        try:
            cancel_document(obj, request.user)
            messages.success(request, f'Adjustment {obj.document_number} cancelled.')
        except ValueError as e:
            messages.error(request, str(e))
    return redirect_back(request, 'adjustment_detail', pk=pk)


@login_required
@warehouse_access
@write_denied_for_viewer
def damaged_post_view(request, pk):
    obj = get_object_or_404(DamagedReport, pk=pk)
    if request.method == 'POST':
        try:
            obj = post_damaged_report(obj, request.user)
            from inventory.services import format_skipped_lines_message
            warning = format_skipped_lines_message(obj)
            if warning:
                messages.warning(request, warning)
            else:
                messages.success(request, f'Damaged Report {obj.document_number} posted. Stock updated.')
        except ValueError as e:
            messages.error(request, str(e))
    return redirect_back(request, 'damaged_detail', pk=pk)


@login_required
@warehouse_access
@write_denied_for_viewer
def damaged_cancel_view(request, pk):
    obj = get_object_or_404(DamagedReport, pk=pk)
    if request.method == 'POST':
        try:
            cancel_document(obj, request.user)
            messages.success(request, f'Damaged Report {obj.document_number} cancelled.')
        except ValueError as e:
            messages.error(request, str(e))
    return redirect_back(request, 'damaged_detail', pk=pk)


# ── Template Views ─────────────────────────────────────────────────────────

@login_required
@warehouse_access
def item_inventory_view(request):
    """Full item inventory summary — shows every item with total stock across all warehouses."""
    from decimal import Decimal
    from django.db.models.functions import Coalesce
    from catalog.models import Item
    from warehouses.models import Warehouse

    warehouse_id = request.GET.get('warehouse')
    item_type = request.GET.get('type')
    search = request.GET.get('q', '')
    warehouses = Warehouse.objects.filter(is_active=True)

    items = Item.objects.select_related('category', 'default_unit').all()
    if item_type:
        items = items.filter(item_type=item_type)
    if search:
        items = items.filter(name__icontains=search) | items.filter(code__icontains=search)

    bal_qs = StockBalance.objects.all()
    if warehouse_id:
        bal_qs = bal_qs.filter(location__warehouse_id=warehouse_id)

    item_totals = bal_qs.values('item_id').annotate(
        total_on_hand=Coalesce(Sum('qty_on_hand'), Decimal('0')),
        total_reserved=Coalesce(Sum('qty_reserved'), Decimal('0')),
    )
    totals_map = {row['item_id']: row for row in item_totals}

    rows = []
    grand_on_hand = Decimal('0')
    grand_value = Decimal('0')
    for item in items:
        t = totals_map.get(item.pk, {'total_on_hand': Decimal('0'), 'total_reserved': Decimal('0')})
        on_hand = t['total_on_hand']
        reserved = t['total_reserved']
        available = on_hand - reserved
        # Per-row value shows the real (possibly negative) amount so the user
        # can spot over-dispatched items.  Only positive stock contributes to
        # the grand total — negative stock is excluded (no negative inventory).
        value = on_hand * (item.cost_price or Decimal('0'))
        rows.append({
            'item': item,
            'on_hand': on_hand,
            'reserved': reserved,
            'available': available,
            'value': value,
        })
        grand_on_hand += on_hand
        if on_hand > Decimal('0'):
            grand_value += value

    return render(request, 'inventory/item_inventory.html', {
        'rows': rows,
        'warehouses': warehouses,
        'selected_warehouse': warehouse_id,
        'current_type': item_type,
        'search': search,
        'grand_on_hand': grand_on_hand,
        'grand_value': grand_value,
        'item_count': len(rows),
    })


STOCK_MOVE_SORT_MAP = {
    'type': 'move_type',
    'item': 'item__code',
    'qty': 'qty',
    'unit': 'unit__abbreviation',
    'from': 'from_location__code',
    'to': 'to_location__code',
    'batch': 'batch_number',
    'serial': 'serial_number',
    'reference': 'reference_number',
    'posted_by': 'created_by__username',
    'posted_at': 'posted_at',
}


@login_required
@warehouse_access
def stock_move_list_view(request):
    from core.utils import sort_queryset, paginate_queryset, search_queryset
    moves = StockMove.objects.filter(status='POSTED').select_related(
        'item', 'unit', 'from_location', 'to_location', 'created_by'
    )
    moves = search_queryset(request, moves, [
        'item__code', 'item__name', 'reference_number', 'batch_number', 'serial_number',
    ])
    type_filter = (request.GET.get('type') or '').strip()
    if type_filter:
        moves = moves.filter(move_type=type_filter)
    moves, sort, direction = sort_queryset(
        request, moves, STOCK_MOVE_SORT_MAP, default_key='posted_at', default_dir='desc'
    )

    # Get total count (no pagination - DataTables handles it client-side)
    total_count = moves.count()

    page_obj = paginate_queryset(request, moves, per_page=25)

    filters = [{
        'param': 'type',
        'label': 'Type',
        'options': list(MoveType.choices),
    }]

    return render(request, 'inventory/stock_move_list.html', {
        'moves': page_obj,
        'total_count': total_count,
        'page_obj': page_obj,
        'sort': sort,
        'dir': direction,
        'filters': filters,
    })


TRANSFER_SORT_MAP = {
    'document_number': 'document_number',
    'from_warehouse': 'from_warehouse__code',
    'to_warehouse': 'to_warehouse__code',
    'status': 'status',
    'created_by': 'created_by__username',
    'created_at': 'created_at',
}


@login_required
@warehouse_access
def transfer_list_view(request):
    from core.utils import sort_queryset, paginate_queryset, search_queryset
    transfers = StockTransfer.objects.select_related(
        'from_warehouse', 'to_warehouse', 'created_by'
    ).all()
    transfers = search_queryset(request, transfers, [
        'document_number', 'from_warehouse__code', 'to_warehouse__code',
    ])
    status_filter = (request.GET.get('status') or '').strip()
    if status_filter:
        transfers = transfers.filter(status=status_filter)
    transfers, sort, direction = sort_queryset(
        request, transfers, TRANSFER_SORT_MAP, default_key='created_at', default_dir='desc'
    )
    page_obj = paginate_queryset(request, transfers, per_page=25)
    filters = [{
        'param': 'status',
        'label': 'Status',
        'options': list(DocumentStatus.choices),
    }]
    return render(request, 'inventory/transfer_list.html', {
        'transfers': page_obj,
        'page_obj': page_obj,
        'sort': sort,
        'dir': direction,
        'filters': filters,
    })


@login_required
@warehouse_access
def transfer_detail_view(request, pk):
    transfer = get_object_or_404(
        StockTransfer.objects.select_related('from_warehouse', 'to_warehouse', 'created_by', 'posted_by')
        .prefetch_related('lines__item', 'lines__unit', 'lines__from_location', 'lines__to_location'), pk=pk
    )
    return render(request, 'inventory/transfer_detail.html', {'transfer': transfer})


ADJUSTMENT_SORT_MAP = {
    'document_number': 'document_number',
    'warehouse': 'warehouse__code',
    'reason': 'reason',
    'status': 'status',
    'created_by': 'created_by__username',
    'created_at': 'created_at',
}


@login_required
@adjustment_access
def adjustment_list_view(request):
    from core.utils import sort_queryset, paginate_queryset, search_queryset
    adjustments = StockAdjustment.objects.select_related(
        'warehouse', 'created_by'
    ).all()
    adjustments = search_queryset(request, adjustments, ['document_number', 'warehouse__code'])
    status_filter = (request.GET.get('status') or '').strip()
    if status_filter:
        adjustments = adjustments.filter(status=status_filter)
    adjustments, sort, direction = sort_queryset(
        request, adjustments, ADJUSTMENT_SORT_MAP, default_key='created_at', default_dir='desc'
    )
    page_obj = paginate_queryset(request, adjustments, per_page=25)
    filters = [{
        'param': 'status',
        'label': 'Status',
        'options': list(DocumentStatus.choices),
    }]
    return render(request, 'inventory/adjustment_list.html', {
        'adjustments': page_obj,
        'page_obj': page_obj,
        'sort': sort,
        'dir': direction,
        'filters': filters,
    })


@login_required
@adjustment_access
def adjustment_detail_view(request, pk):
    adjustment = get_object_or_404(
        StockAdjustment.objects.select_related('warehouse', 'created_by', 'approved_by', 'posted_by')
        .prefetch_related('lines__item', 'lines__unit', 'lines__location'), pk=pk
    )

    # Check for pending (non-posted) stock movement documents in the same warehouse
    pending_docs = {}
    if adjustment.status == DocumentStatus.DRAFT:
        from procurement.models import GoodsReceipt
        from sales.models import DeliveryNote, SalesPickup
        from services.models import CustomerService

        wh = adjustment.warehouse
        pending_statuses = [DocumentStatus.DRAFT, DocumentStatus.APPROVED]

        grn_count = GoodsReceipt.objects.filter(warehouse=wh, status__in=pending_statuses).count()
        if grn_count:
            pending_docs['GRNs'] = grn_count

        dn_count = DeliveryNote.objects.filter(warehouse=wh, status__in=pending_statuses).count()
        if dn_count:
            pending_docs['Deliveries'] = dn_count

        pickup_count = SalesPickup.objects.filter(warehouse=wh, status__in=pending_statuses).count()
        if pickup_count:
            pending_docs['Pickups'] = pickup_count

        svc_count = CustomerService.objects.filter(
            warehouse=wh, status__in=['DRAFT', 'IN_PROGRESS']
        ).count()
        if svc_count:
            pending_docs['Services'] = svc_count

    return render(request, 'inventory/adjustment_detail.html', {
        'adjustment': adjustment,
        'pending_docs': pending_docs,
    })


DAMAGED_SORT_MAP = {
    'document_number': 'document_number',
    'warehouse': 'warehouse__code',
    'status': 'status',
    'created_by': 'created_by__username',
    'created_at': 'created_at',
}


@login_required
@warehouse_access
def damaged_list_view(request):
    from core.utils import sort_queryset, paginate_queryset, search_queryset
    reports = DamagedReport.objects.select_related(
        'warehouse', 'created_by'
    ).all()
    reports = search_queryset(request, reports, ['document_number', 'warehouse__code'])
    status_filter = (request.GET.get('status') or '').strip()
    if status_filter:
        reports = reports.filter(status=status_filter)
    reports, sort, direction = sort_queryset(
        request, reports, DAMAGED_SORT_MAP, default_key='created_at', default_dir='desc'
    )
    page_obj = paginate_queryset(request, reports, per_page=25)
    filters = [{
        'param': 'status',
        'label': 'Status',
        'options': list(DocumentStatus.choices),
    }]
    return render(request, 'inventory/damaged_list.html', {
        'reports': page_obj,
        'page_obj': page_obj,
        'sort': sort,
        'dir': direction,
        'filters': filters,
    })


@login_required
@warehouse_access
def damaged_detail_view(request, pk):
    report = get_object_or_404(
        DamagedReport.objects.select_related('warehouse', 'created_by', 'posted_by')
        .prefetch_related('lines__item', 'lines__unit', 'lines__location'), pk=pk
    )
    return render(request, 'inventory/damaged_detail.html', {'report': report})


# ── Transfer CRUD ──────────────────────────────────────────────────────────

@login_required
@warehouse_access
@write_denied_for_viewer
def transfer_create_view(request):
    if request.method == 'POST':
        form = StockTransferForm(request.POST)
        formset = StockTransferLineFormSet(request.POST)
        form_valid = form.is_valid()
        formset_valid = formset.is_valid()
        if form_valid and formset_valid:
            obj = form.save(commit=False)
            obj.created_by = request.user
            save_with_document_number(obj, 'TR', StockTransfer)
            formset.instance = obj
            formset.save()
            messages.success(request, f'Transfer {obj.document_number} created.')
            return redirect('transfer_list')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = StockTransferForm()
        formset = StockTransferLineFormSet()
    return render(request, 'inventory/transfer_form.html', {
        'form': form, 'formset': formset, 'title': 'Create Stock Transfer',
    })


@login_required
@warehouse_access
@write_denied_for_viewer
def transfer_edit_view(request, pk):
    obj = get_object_or_404(StockTransfer, pk=pk)
    if obj.status != 'DRAFT':
        messages.error(request, 'Only DRAFT transfers can be edited.')
        return redirect('transfer_list')
    if request.method == 'POST':
        form = StockTransferForm(request.POST, instance=obj)
        formset = StockTransferLineFormSet(request.POST, instance=obj)
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            messages.success(request, f'Transfer {obj.document_number} updated.')
            return redirect('transfer_list')
    else:
        form = StockTransferForm(instance=obj)
        formset = StockTransferLineFormSet(instance=obj)
    return render(request, 'inventory/transfer_form.html', {
        'form': form, 'formset': formset, 'title': f'Edit Transfer: {obj.document_number}',
    })


@login_required
@warehouse_access
@write_denied_for_viewer
def transfer_delete_view(request, pk):
    obj = get_object_or_404(StockTransfer, pk=pk)
    if request.method == 'POST':
        obj.soft_delete()
        messages.success(request, f'Transfer {obj.document_number} deleted.')
        return redirect('transfer_list')
    return render(request, 'inventory/transfer_delete.html', {'object': obj})


# ── Adjustment CRUD ────────────────────────────────────────────────────────

@login_required
@adjustment_access
@write_denied_for_viewer
def adjustment_create_view(request):
    if request.method == 'POST':
        form = StockAdjustmentForm(request.POST)
        formset = StockAdjustmentLineFormSet(request.POST)
        form_valid = form.is_valid()
        formset_valid = formset.is_valid()
        if form_valid and formset_valid:
            obj = form.save(commit=False)
            obj.created_by = request.user
            save_with_document_number(obj, 'ADJ', StockAdjustment)
            formset.instance = obj
            formset.save()
            messages.success(request, f'Adjustment {obj.document_number} created.')
            return redirect('adjustment_list')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = StockAdjustmentForm()
        formset = StockAdjustmentLineFormSet()
    return render(request, 'inventory/adjustment_form.html', {
        'form': form, 'formset': formset, 'title': 'Create Stock Adjustment',
    })


@login_required
@adjustment_access
@write_denied_for_viewer
def adjustment_edit_view(request, pk):
    obj = get_object_or_404(StockAdjustment, pk=pk)
    if obj.status != 'DRAFT':
        messages.error(request, 'Only DRAFT adjustments can be edited.')
        return redirect('adjustment_list')
    if request.method == 'POST':
        form = StockAdjustmentForm(request.POST, instance=obj)
        formset = StockAdjustmentLineFormSet(request.POST, instance=obj)
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            messages.success(request, f'Adjustment {obj.document_number} updated.')
            return redirect('adjustment_list')
    else:
        form = StockAdjustmentForm(instance=obj)
        formset = StockAdjustmentLineFormSet(instance=obj)
    return render(request, 'inventory/adjustment_form.html', {
        'form': form, 'formset': formset, 'title': f'Edit Adjustment: {obj.document_number}',
    })


@login_required
@adjustment_access
@write_denied_for_viewer
def adjustment_delete_view(request, pk):
    obj = get_object_or_404(StockAdjustment, pk=pk)
    if request.method == 'POST':
        obj.soft_delete()
        messages.success(request, f'Adjustment {obj.document_number} deleted.')
        return redirect('adjustment_list')
    return render(request, 'inventory/adjustment_delete.html', {'object': obj})


# ── Damaged Report CRUD ────────────────────────────────────────────────────

@login_required
@warehouse_access
@write_denied_for_viewer
def damaged_create_view(request):
    if request.method == 'POST':
        form = DamagedReportForm(request.POST)
        formset = DamagedReportLineFormSet(request.POST, request.FILES)
        form_valid = form.is_valid()
        formset_valid = formset.is_valid()
        if form_valid and formset_valid:
            obj = form.save(commit=False)
            obj.created_by = request.user
            save_with_document_number(obj, 'DAM', DamagedReport)
            formset.instance = obj
            formset.save()
            messages.success(request, f'Damaged Report {obj.document_number} created.')
            return redirect('damaged_list')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = DamagedReportForm()
        formset = DamagedReportLineFormSet()
    return render(request, 'inventory/damaged_form.html', {
        'form': form, 'formset': formset, 'title': 'Create Damaged Report',
    })


@login_required
@warehouse_access
@write_denied_for_viewer
def damaged_edit_view(request, pk):
    obj = get_object_or_404(DamagedReport, pk=pk)
    if obj.status != 'DRAFT':
        messages.error(request, 'Only DRAFT damaged reports can be edited.')
        return redirect('damaged_list')
    if request.method == 'POST':
        form = DamagedReportForm(request.POST, instance=obj)
        formset = DamagedReportLineFormSet(request.POST, request.FILES, instance=obj)
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            messages.success(request, f'Damaged Report {obj.document_number} updated.')
            return redirect('damaged_list')
    else:
        form = DamagedReportForm(instance=obj)
        formset = DamagedReportLineFormSet(instance=obj)
    return render(request, 'inventory/damaged_form.html', {
        'form': form, 'formset': formset, 'title': f'Edit Damaged Report: {obj.document_number}',
    })


@login_required
@warehouse_access
@write_denied_for_viewer
def damaged_delete_view(request, pk):
    obj = get_object_or_404(DamagedReport, pk=pk)
    if request.method == 'POST':
        obj.soft_delete()
        messages.success(request, f'Damaged Report {obj.document_number} deleted.')
        return redirect('damaged_list')
    return render(request, 'inventory/damaged_delete.html', {'object': obj})


# ── Inventory-to-Supply Transfer (IST) ─────────────────────────────────────

IST_SORT_MAP = {
    'document_number': 'document_number',
    'warehouse': 'warehouse__code',
    'transfer_date': 'transfer_date',
    'reason': 'reason',
    'status': 'status',
    'created_by': 'created_by__username',
}


@login_required
@warehouse_access
def ist_list_view(request):
    from core.utils import sort_queryset, paginate_queryset, search_queryset
    transfers = InventoryToSupplyTransfer.objects.select_related(
        'warehouse', 'created_by'
    ).all()
    transfers = search_queryset(request, transfers, ['document_number', 'warehouse__code'])
    status_filter = (request.GET.get('status') or '').strip()
    if status_filter:
        transfers = transfers.filter(status=status_filter)
    transfers, sort, direction = sort_queryset(
        request, transfers, IST_SORT_MAP, default_key='created_at', default_dir='desc'
    )
    page_obj = paginate_queryset(request, transfers, per_page=25)
    filters = [{
        'param': 'status',
        'label': 'Status',
        'options': list(DocumentStatus.choices),
    }]
    return render(request, 'inventory/ist_list.html', {
        'transfers': page_obj,
        'page_obj': page_obj,
        'sort': sort,
        'dir': direction,
        'filters': filters,
    })


@login_required
@warehouse_access
def ist_detail_view(request, pk):
    transfer = get_object_or_404(
        InventoryToSupplyTransfer.objects
        .select_related('warehouse', 'created_by', 'posted_by')
        .prefetch_related('lines__item', 'lines__unit', 'lines__location', 'lines__supply_item'),
        pk=pk,
    )
    return render(request, 'inventory/ist_detail.html', {'transfer': transfer})


@login_required
@warehouse_access
@write_denied_for_viewer
def ist_create_view(request):
    if request.method == 'POST':
        form = InventoryToSupplyTransferForm(request.POST)
        formset = InventoryToSupplyTransferLineFormSet(request.POST)
        form_valid = form.is_valid()
        formset_valid = formset.is_valid()
        if form_valid and formset_valid:
            obj = form.save(commit=False)
            obj.created_by = request.user
            save_with_document_number(obj, 'IST', InventoryToSupplyTransfer)
            formset.instance = obj
            formset.save()
            messages.success(request, f'Transfer {obj.document_number} created.')
            return redirect('ist_detail', pk=obj.pk)
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = InventoryToSupplyTransferForm(initial={
            'transfer_date': timezone.now().date(),
        })
        formset = InventoryToSupplyTransferLineFormSet()
    return render(request, 'inventory/ist_form.html', {
        'form': form, 'formset': formset, 'title': 'New Inventory → Supply Transfer',
    })


@login_required
@warehouse_access
@write_denied_for_viewer
def ist_edit_view(request, pk):
    obj = get_object_or_404(InventoryToSupplyTransfer, pk=pk)
    if obj.status != 'DRAFT':
        messages.error(request, 'Only DRAFT transfers can be edited.')
        return redirect('ist_detail', pk=pk)
    if request.method == 'POST':
        form = InventoryToSupplyTransferForm(request.POST, instance=obj)
        formset = InventoryToSupplyTransferLineFormSet(request.POST, instance=obj)
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            messages.success(request, f'Transfer {obj.document_number} updated.')
            return redirect('ist_detail', pk=obj.pk)
    else:
        form = InventoryToSupplyTransferForm(instance=obj)
        formset = InventoryToSupplyTransferLineFormSet(instance=obj)
    return render(request, 'inventory/ist_form.html', {
        'form': form, 'formset': formset,
        'title': f'Edit Transfer: {obj.document_number}', 'object': obj,
    })


@login_required
@warehouse_access
@write_denied_for_viewer
def ist_delete_view(request, pk):
    obj = get_object_or_404(InventoryToSupplyTransfer, pk=pk)
    if request.method == 'POST':
        obj.soft_delete()
        messages.success(request, f'Transfer {obj.document_number} deleted.')
        return redirect('ist_list')
    return render(request, 'inventory/ist_delete.html', {'object': obj})


@login_required
@warehouse_access
@write_denied_for_viewer
def ist_post_view(request, pk):
    obj = get_object_or_404(InventoryToSupplyTransfer, pk=pk)
    if request.method == 'POST':
        try:
            obj = post_inventory_to_supply(obj, request.user)
            from inventory.services import format_skipped_lines_message
            warning = format_skipped_lines_message(obj)
            if warning:
                messages.warning(request, warning)
            else:
                messages.success(
                    request,
                    f'Transfer {obj.document_number} posted. '
                    f'Inventory deducted and supply stock updated.',
                )
        except ValueError as e:
            messages.error(request, str(e))
    return redirect_back(request, 'ist_detail', pk=pk)


@login_required
@warehouse_access
@write_denied_for_viewer
def ist_cancel_view(request, pk):
    obj = get_object_or_404(InventoryToSupplyTransfer, pk=pk)
    if request.method == 'POST':
        try:
            cancel_inventory_to_supply(obj, request.user)
            messages.success(request, f'Transfer {obj.document_number} cancelled. Inventory and supply stock reversed.')
        except ValueError as e:
            messages.error(request, str(e))
    return redirect_back(request, 'ist_detail', pk=pk)
