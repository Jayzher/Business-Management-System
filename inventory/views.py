from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum, F
from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from inventory.models import (
    StockMove, StockBalance,
    StockAdjustment, StockAdjustmentLine,
    DamagedReport, DamagedReportLine,
    StockTransfer, StockTransferLine,
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
)
from django.utils import timezone
from inventory.services import (
    post_transfer, post_adjustment, post_damaged_report, cancel_document,
)
from core.models import DocumentStatus
from accounts.decorators import warehouse_access


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
            post_transfer(transfer, request.user)
            return Response({'status': 'posted', 'document_number': transfer.document_number})
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class StockAdjustmentViewSet(viewsets.ModelViewSet):
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
            post_adjustment(adjustment, request.user)
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
            post_damaged_report(report, request.user)
            return Response({'status': 'posted', 'document_number': report.document_number})
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


# ── Template Action Views ───────────────────────────────────────────────────

@login_required
@warehouse_access
def transfer_post_view(request, pk):
    obj = get_object_or_404(StockTransfer, pk=pk)
    if request.method == 'POST':
        try:
            post_transfer(obj, request.user)
            messages.success(request, f'Transfer {obj.document_number} posted. Stock updated.')
        except ValueError as e:
            messages.error(request, str(e))
    return redirect('transfer_detail', pk=pk)


@login_required
@warehouse_access
def transfer_cancel_view(request, pk):
    obj = get_object_or_404(StockTransfer, pk=pk)
    if request.method == 'POST':
        try:
            cancel_document(obj, request.user)
            messages.success(request, f'Transfer {obj.document_number} cancelled.')
        except ValueError as e:
            messages.error(request, str(e))
    return redirect('transfer_detail', pk=pk)


@login_required
@warehouse_access
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
    return redirect('adjustment_detail', pk=pk)


@login_required
@warehouse_access
def adjustment_post_view(request, pk):
    obj = get_object_or_404(StockAdjustment, pk=pk)
    if request.method == 'POST':
        try:
            post_adjustment(obj, request.user)
            messages.success(request, f'Adjustment {obj.document_number} posted. Stock updated.')
        except ValueError as e:
            messages.error(request, str(e))
    return redirect('adjustment_detail', pk=pk)


@login_required
@warehouse_access
def adjustment_cancel_view(request, pk):
    obj = get_object_or_404(StockAdjustment, pk=pk)
    if request.method == 'POST':
        try:
            cancel_document(obj, request.user)
            messages.success(request, f'Adjustment {obj.document_number} cancelled.')
        except ValueError as e:
            messages.error(request, str(e))
    return redirect('adjustment_detail', pk=pk)


@login_required
@warehouse_access
def damaged_post_view(request, pk):
    obj = get_object_or_404(DamagedReport, pk=pk)
    if request.method == 'POST':
        try:
            post_damaged_report(obj, request.user)
            messages.success(request, f'Damaged Report {obj.document_number} posted. Stock updated.')
        except ValueError as e:
            messages.error(request, str(e))
    return redirect('damaged_detail', pk=pk)


@login_required
@warehouse_access
def damaged_cancel_view(request, pk):
    obj = get_object_or_404(DamagedReport, pk=pk)
    if request.method == 'POST':
        try:
            cancel_document(obj, request.user)
            messages.success(request, f'Damaged Report {obj.document_number} cancelled.')
        except ValueError as e:
            messages.error(request, str(e))
    return redirect('damaged_detail', pk=pk)


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
        value = on_hand * (item.cost_price or Decimal('0'))
        rows.append({
            'item': item,
            'on_hand': on_hand,
            'reserved': reserved,
            'available': available,
            'value': value,
        })
        grand_on_hand += on_hand
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


@login_required
@warehouse_access
def stock_move_list_view(request):
    moves = StockMove.objects.filter(status='POSTED').select_related(
        'item', 'unit', 'from_location', 'to_location', 'created_by'
    )[:100]
    return render(request, 'inventory/stock_move_list.html', {'moves': moves})


@login_required
@warehouse_access
def transfer_list_view(request):
    transfers = StockTransfer.objects.select_related(
        'from_warehouse', 'to_warehouse', 'created_by'
    ).all()
    return render(request, 'inventory/transfer_list.html', {'transfers': transfers})


@login_required
@warehouse_access
def transfer_detail_view(request, pk):
    transfer = get_object_or_404(
        StockTransfer.objects.select_related('from_warehouse', 'to_warehouse', 'created_by', 'posted_by')
        .prefetch_related('lines__item', 'lines__unit', 'lines__from_location', 'lines__to_location'), pk=pk
    )
    return render(request, 'inventory/transfer_detail.html', {'transfer': transfer})


@login_required
@warehouse_access
def adjustment_list_view(request):
    adjustments = StockAdjustment.objects.select_related(
        'warehouse', 'created_by'
    ).all()
    return render(request, 'inventory/adjustment_list.html', {'adjustments': adjustments})


@login_required
@warehouse_access
def adjustment_detail_view(request, pk):
    adjustment = get_object_or_404(
        StockAdjustment.objects.select_related('warehouse', 'created_by', 'approved_by', 'posted_by')
        .prefetch_related('lines__item', 'lines__unit', 'lines__location'), pk=pk
    )
    return render(request, 'inventory/adjustment_detail.html', {'adjustment': adjustment})


@login_required
@warehouse_access
def damaged_list_view(request):
    reports = DamagedReport.objects.select_related(
        'warehouse', 'created_by'
    ).all()
    return render(request, 'inventory/damaged_list.html', {'reports': reports})


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
def transfer_create_view(request):
    if request.method == 'POST':
        form = StockTransferForm(request.POST)
        formset = StockTransferLineFormSet(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.created_by = request.user
            obj.save()
            formset = StockTransferLineFormSet(request.POST, instance=obj)
            if formset.is_valid():
                formset.save()
                messages.success(request, f'Transfer {obj.document_number} created.')
                return redirect('transfer_list')
    else:
        form = StockTransferForm()
        formset = StockTransferLineFormSet()
    return render(request, 'inventory/transfer_form.html', {
        'form': form, 'formset': formset, 'title': 'Create Stock Transfer',
    })


@login_required
@warehouse_access
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
def transfer_delete_view(request, pk):
    obj = get_object_or_404(StockTransfer, pk=pk)
    if request.method == 'POST':
        obj.soft_delete()
        messages.success(request, f'Transfer {obj.document_number} deleted.')
        return redirect('transfer_list')
    return render(request, 'inventory/transfer_delete.html', {'object': obj})


# ── Adjustment CRUD ────────────────────────────────────────────────────────

@login_required
@warehouse_access
def adjustment_create_view(request):
    if request.method == 'POST':
        form = StockAdjustmentForm(request.POST)
        formset = StockAdjustmentLineFormSet(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.created_by = request.user
            obj.save()
            formset = StockAdjustmentLineFormSet(request.POST, instance=obj)
            if formset.is_valid():
                formset.save()
                messages.success(request, f'Adjustment {obj.document_number} created.')
                return redirect('adjustment_list')
    else:
        form = StockAdjustmentForm()
        formset = StockAdjustmentLineFormSet()
    return render(request, 'inventory/adjustment_form.html', {
        'form': form, 'formset': formset, 'title': 'Create Stock Adjustment',
    })


@login_required
@warehouse_access
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
@warehouse_access
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
def damaged_create_view(request):
    if request.method == 'POST':
        form = DamagedReportForm(request.POST)
        formset = DamagedReportLineFormSet(request.POST, request.FILES)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.created_by = request.user
            obj.save()
            formset = DamagedReportLineFormSet(request.POST, request.FILES, instance=obj)
            if formset.is_valid():
                formset.save()
                messages.success(request, f'Damaged Report {obj.document_number} created.')
                return redirect('damaged_list')
    else:
        form = DamagedReportForm()
        formset = DamagedReportLineFormSet()
    return render(request, 'inventory/damaged_form.html', {
        'form': form, 'formset': formset, 'title': 'Create Damaged Report',
    })


@login_required
@warehouse_access
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
def damaged_delete_view(request, pk):
    obj = get_object_or_404(DamagedReport, pk=pk)
    if request.method == 'POST':
        obj.soft_delete()
        messages.success(request, f'Damaged Report {obj.document_number} deleted.')
        return redirect('damaged_list')
    return render(request, 'inventory/damaged_delete.html', {'object': obj})
