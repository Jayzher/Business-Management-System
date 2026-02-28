from decimal import Decimal
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from pos.models import (
    POSRegister, POSShift, POSSale, POSSaleLine,
    POSPayment, POSRefund, POSRefundLine, CashEntry,
    ShiftStatus, SaleStatus, PaymentMethod,
)
from pos.serializers import (
    POSRegisterSerializer, POSShiftSerializer,
    POSSaleSerializer, POSSaleLineSerializer,
    POSPaymentSerializer, POSRefundSerializer,
    CashEntrySerializer,
    OpenShiftRequestSerializer, CloseShiftRequestSerializer,
    AddLineRequestSerializer, SetPaymentsRequestSerializer,
    CreateRefundRequestSerializer,
)
from pos.services import (
    open_shift, close_shift,
    post_pos_sale, post_pos_refund, void_sale,
    generate_sale_number, generate_refund_number,
)
from pos.forms import POSRegisterForm, OpenShiftForm, CloseShiftForm, CashEntryForm


# ── DRF API Views ─────────────────────────────────────────────────────────

class POSRegisterViewSet(viewsets.ModelViewSet):
    queryset = POSRegister.objects.select_related(
        'warehouse', 'default_location', 'price_list'
    ).all()
    serializer_class = POSRegisterSerializer
    filterset_fields = ['warehouse', 'is_active']


class POSShiftViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = POSShift.objects.select_related('register', 'opened_by', 'closed_by').all()
    serializer_class = POSShiftSerializer
    filterset_fields = ['register', 'status']


class POSSaleViewSet(viewsets.ModelViewSet):
    queryset = POSSale.objects.select_related(
        'register', 'shift', 'warehouse', 'location', 'customer', 'created_by',
    ).prefetch_related('lines__item', 'lines__unit', 'payments').all()
    serializer_class = POSSaleSerializer
    filterset_fields = ['status', 'shift', 'register']
    search_fields = ['sale_no']

    @action(detail=True, methods=['post'], url_path='add-line')
    def add_line(self, request, pk=None):
        sale = self.get_object()
        if sale.status != SaleStatus.DRAFT:
            return Response({'error': 'Can only add lines to DRAFT sales.'}, status=status.HTTP_400_BAD_REQUEST)

        ser = AddLineRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data

        from catalog.models import Item, Unit
        item = get_object_or_404(Item, pk=d['item'])
        unit = get_object_or_404(Unit, pk=d['unit'])

        line_total = (d['qty'] * d['unit_price']) - d.get('discount_amount', 0)
        tax_amount = line_total * (d.get('tax_rate', 0) / 100)
        line_total_with_tax = line_total + tax_amount

        line = POSSaleLine.objects.create(
            sale=sale,
            item=item,
            location_id=d.get('location'),
            qty=d['qty'],
            unit=unit,
            unit_price=d['unit_price'],
            discount_amount=d.get('discount_amount', 0),
            tax_rate=d.get('tax_rate', 0),
            line_total=line_total_with_tax,
            batch_number=d.get('batch_number', ''),
            serial_number=d.get('serial_number', ''),
            qr_uid_used=d.get('qr_uid_used'),
        )

        _recalculate_sale_totals(sale)
        return Response(POSSaleLineSerializer(line).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='set-payments')
    def set_payments(self, request, pk=None):
        sale = self.get_object()
        if sale.status != SaleStatus.DRAFT:
            return Response({'error': 'Can only set payments on DRAFT sales.'}, status=status.HTTP_400_BAD_REQUEST)

        payments_data = request.data.get('payments', [])
        if not payments_data:
            return Response({'error': 'No payments provided.'}, status=status.HTTP_400_BAD_REQUEST)

        sale.payments.all().delete()
        for p in payments_data:
            POSPayment.objects.create(
                sale=sale,
                method=p['method'],
                amount=Decimal(str(p['amount'])),
                reference_no=p.get('reference_no', ''),
            )
        return Response({'status': 'payments_set', 'count': len(payments_data)})

    @action(detail=True, methods=['post'], url_path='mark-paid')
    def mark_paid(self, request, pk=None):
        sale = self.get_object()
        if sale.status != SaleStatus.DRAFT:
            return Response({'error': 'Sale is not in DRAFT status.'}, status=status.HTTP_400_BAD_REQUEST)

        payment_sum = sum(p.amount for p in sale.payments.all())
        if payment_sum < sale.grand_total:
            return Response(
                {'error': f'Payments ({payment_sum}) < grand total ({sale.grand_total}).'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        sale.status = SaleStatus.PAID
        sale.save(update_fields=['status', 'updated_at'])
        return Response({'status': 'paid', 'sale_no': sale.sale_no})

    @action(detail=True, methods=['post'], url_path='post')
    def post_sale(self, request, pk=None):
        sale = self.get_object()
        try:
            post_pos_sale(sale.pk, request.user)
            sale.refresh_from_db()
            return Response({'status': 'posted', 'sale_no': sale.sale_no})
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def void(self, request, pk=None):
        sale = self.get_object()
        try:
            void_sale(sale.pk, request.user)
            return Response({'status': 'voided', 'sale_no': sale.sale_no})
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class POSRefundViewSet(viewsets.ModelViewSet):
    queryset = POSRefund.objects.select_related(
        'original_sale', 'shift', 'created_by',
    ).prefetch_related('lines').all()
    serializer_class = POSRefundSerializer
    filterset_fields = ['status', 'shift']

    @action(detail=True, methods=['post'], url_path='post')
    def post_refund(self, request, pk=None):
        refund = self.get_object()
        try:
            post_pos_refund(refund.pk, request.user)
            refund.refresh_from_db()
            return Response({'status': 'posted', 'refund_no': refund.refund_no})
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class CashEntryViewSet(viewsets.ModelViewSet):
    queryset = CashEntry.objects.select_related('shift', 'created_by').all()
    serializer_class = CashEntrySerializer
    filterset_fields = ['shift', 'entry_type']

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


# ── Shift API endpoints ───────────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_open_shift(request):
    ser = OpenShiftRequestSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    register = get_object_or_404(POSRegister, pk=ser.validated_data['register'])
    try:
        shift = open_shift(register, request.user, ser.validated_data.get('opening_cash', 0))
        return Response(POSShiftSerializer(shift).data, status=status.HTTP_201_CREATED)
    except ValueError as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_close_shift(request, pk):
    shift = get_object_or_404(POSShift, pk=pk)
    ser = CloseShiftRequestSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    try:
        shift = close_shift(shift, request.user, ser.validated_data['closing_cash_declared'])
        return Response(POSShiftSerializer(shift).data)
    except ValueError as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_shift_summary(request, pk):
    shift = get_object_or_404(POSShift, pk=pk)
    return Response(POSShiftSerializer(shift).data)


# ── Helper ─────────────────────────────────────────────────────────────────

def _recalculate_sale_totals(sale):
    """Recalculate sale subtotal, discount_total, tax_total, grand_total from lines."""
    lines = sale.lines.all()
    subtotal = sum(l.qty * l.unit_price for l in lines)
    discount_total = sum(l.discount_amount for l in lines)
    tax_total = sum((l.qty * l.unit_price - l.discount_amount) * l.tax_rate / 100 for l in lines)
    grand_total = subtotal - discount_total + tax_total

    sale.subtotal = subtotal
    sale.discount_total = discount_total
    sale.tax_total = tax_total
    sale.grand_total = grand_total
    sale.save(update_fields=['subtotal', 'discount_total', 'tax_total', 'grand_total', 'updated_at'])


# ── Template Views ─────────────────────────────────────────────────────────

@login_required
def register_list_view(request):
    registers = POSRegister.objects.select_related('warehouse', 'default_location', 'price_list').all()
    return render(request, 'pos/register_list.html', {'registers': registers})


@login_required
def register_create_view(request):
    if request.method == 'POST':
        form = POSRegisterForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Register created.')
            return redirect('pos_register_list')
    else:
        form = POSRegisterForm()
    return render(request, 'pos/register_form.html', {'form': form, 'title': 'Create Register'})


@login_required
def register_edit_view(request, pk):
    obj = get_object_or_404(POSRegister, pk=pk)
    if request.method == 'POST':
        form = POSRegisterForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, 'Register updated.')
            return redirect('pos_register_list')
    else:
        form = POSRegisterForm(instance=obj)
    return render(request, 'pos/register_form.html', {'form': form, 'title': f'Edit Register: {obj.name}'})


@login_required
def register_delete_view(request, pk):
    obj = get_object_or_404(POSRegister, pk=pk)
    if request.method == 'POST':
        obj.soft_delete()
        messages.success(request, f'Register "{obj.name}" deleted.')
        return redirect('pos_register_list')
    return render(request, 'pos/register_delete.html', {'object': obj})


@login_required
def shift_open_view(request):
    if request.method == 'POST':
        form = OpenShiftForm(request.POST)
        if form.is_valid():
            try:
                shift = open_shift(
                    form.cleaned_data['register'],
                    request.user,
                    form.cleaned_data['opening_cash'] or 0,
                )
                messages.success(request, f'Shift #{shift.pk} opened.')
                return redirect('pos_terminal', shift_id=shift.pk)
            except ValueError as e:
                messages.error(request, str(e))
    else:
        form = OpenShiftForm()
    return render(request, 'pos/shift_open.html', {'form': form})


@login_required
def shift_close_view(request, pk):
    shift = get_object_or_404(POSShift, pk=pk)
    if shift.status != ShiftStatus.OPEN:
        messages.error(request, 'Shift is already closed.')
        return redirect('pos_shift_list')
    if request.method == 'POST':
        form = CloseShiftForm(request.POST)
        if form.is_valid():
            try:
                shift = close_shift(shift, request.user, form.cleaned_data['closing_cash_declared'])
                messages.success(request, f'Shift #{shift.pk} closed. Variance: {shift.variance}')
                return redirect('pos_shift_summary', pk=shift.pk)
            except ValueError as e:
                messages.error(request, str(e))
    else:
        form = CloseShiftForm()
    return render(request, 'pos/shift_close.html', {'form': form, 'shift': shift})


@login_required
def shift_list_view(request):
    shifts = POSShift.objects.select_related('register', 'opened_by', 'closed_by').all()[:50]
    return render(request, 'pos/shift_list.html', {'shifts': shifts})


@login_required
def shift_summary_view(request, pk):
    shift = get_object_or_404(POSShift.objects.select_related('register', 'opened_by', 'closed_by'), pk=pk)
    sales = POSSale.objects.filter(shift=shift).select_related('customer', 'created_by')
    refunds = POSRefund.objects.filter(shift=shift).select_related('original_sale', 'created_by')
    cash_entries = CashEntry.objects.filter(shift=shift).select_related('created_by')
    return render(request, 'pos/shift_summary.html', {
        'shift': shift,
        'sales': sales,
        'refunds': refunds,
        'cash_entries': cash_entries,
    })


@login_required
def terminal_view(request, shift_id):
    """Main POS terminal checkout page."""
    shift = get_object_or_404(POSShift.objects.select_related('register'), pk=shift_id)
    if shift.status != ShiftStatus.OPEN:
        messages.error(request, 'This shift is closed.')
        return redirect('pos_shift_list')

    register = shift.register
    # Get or create a DRAFT sale for this shift
    sale = POSSale.objects.filter(shift=shift, status=SaleStatus.DRAFT).first()

    return render(request, 'pos/terminal.html', {
        'shift': shift,
        'register': register,
        'sale': sale,
    })


@login_required
def receipt_list_view(request):
    sales = POSSale.objects.filter(
        status__in=[SaleStatus.POSTED, SaleStatus.PAID, SaleStatus.REFUNDED],
    ).select_related('register', 'customer', 'created_by')[:100]
    return render(request, 'pos/receipt_list.html', {'sales': sales})


@login_required
def receipt_detail_view(request, pk):
    sale = get_object_or_404(
        POSSale.objects.select_related('register', 'shift', 'warehouse', 'customer', 'created_by')
        .prefetch_related('lines__item', 'lines__unit', 'payments'),
        pk=pk,
    )
    return render(request, 'pos/receipt_detail.html', {'sale': sale})


@login_required
def refund_create_view(request, sale_pk):
    """Start a refund from an existing posted sale."""
    original_sale = get_object_or_404(
        POSSale.objects.prefetch_related('lines__item', 'lines__unit'),
        pk=sale_pk,
    )
    if original_sale.status not in [SaleStatus.POSTED, SaleStatus.PAID]:
        messages.error(request, 'Can only refund POSTED or PAID sales.')
        return redirect('pos_receipt_detail', pk=sale_pk)

    # Need an open shift
    current_shift = POSShift.objects.filter(
        register=original_sale.register, status=ShiftStatus.OPEN,
    ).first()
    if not current_shift:
        messages.error(request, 'No open shift on this register. Open a shift first.')
        return redirect('pos_receipt_detail', pk=sale_pk)

    if request.method == 'POST':
        reason = request.POST.get('reason', '')
        selected_lines = request.POST.getlist('refund_lines')
        if not selected_lines:
            messages.error(request, 'Select at least one line to refund.')
        else:
            refund = POSRefund.objects.create(
                refund_no=generate_refund_number(),
                original_sale=original_sale,
                shift=current_shift,
                reason=reason,
                created_by=request.user,
            )
            subtotal = Decimal('0')
            for line_id in selected_lines:
                sale_line = original_sale.lines.get(pk=line_id)
                qty = Decimal(request.POST.get(f'qty_{line_id}', str(sale_line.qty)))
                amount = qty * sale_line.unit_price
                POSRefundLine.objects.create(
                    refund=refund,
                    sale_line=sale_line,
                    item=sale_line.item,
                    location=sale_line.location or original_sale.location,
                    qty=qty,
                    unit=sale_line.unit,
                    amount=amount,
                )
                subtotal += amount

            refund.subtotal = subtotal
            refund.grand_total = subtotal
            refund.save(update_fields=['subtotal', 'grand_total', 'updated_at'])

            try:
                post_pos_refund(refund.pk, request.user)
                messages.success(request, f'Refund {refund.refund_no} posted.')
            except ValueError as e:
                messages.error(request, str(e))
            return redirect('pos_receipt_detail', pk=sale_pk)

    return render(request, 'pos/refund_create.html', {
        'original_sale': original_sale,
    })


@login_required
@require_POST
def terminal_new_sale(request, shift_id):
    """Create a new DRAFT sale in the terminal."""
    shift = get_object_or_404(POSShift, pk=shift_id)
    if shift.status != ShiftStatus.OPEN:
        return JsonResponse({'error': 'Shift is closed.'}, status=400)

    register = shift.register
    sale = POSSale.objects.create(
        sale_no=generate_sale_number(),
        register=register,
        shift=shift,
        warehouse=register.warehouse,
        location=register.default_location,
        created_by=request.user,
    )
    return JsonResponse({'sale_id': sale.pk, 'sale_no': sale.sale_no})


@login_required
@require_POST
def terminal_add_line(request, sale_id):
    """Add a line to a DRAFT sale (AJAX endpoint for terminal)."""
    sale = get_object_or_404(POSSale, pk=sale_id)
    if sale.status != SaleStatus.DRAFT:
        return JsonResponse({'error': 'Sale is not in DRAFT.'}, status=400)

    from catalog.models import Item, Unit
    item_id = request.POST.get('item_id')
    qty = Decimal(request.POST.get('qty', '1'))
    discount = Decimal(request.POST.get('discount_amount', '0'))
    tax_rate = Decimal(request.POST.get('tax_rate', '0'))

    item = get_object_or_404(Item, pk=item_id)
    unit = item.default_unit

    unit_price = Decimal(request.POST.get('unit_price', '0'))
    if unit_price <= 0:
        unit_price = item.selling_price

    line_subtotal = qty * unit_price - discount
    tax_amount = line_subtotal * tax_rate / 100
    line_total = line_subtotal + tax_amount

    line = POSSaleLine.objects.create(
        sale=sale,
        item=item,
        location=sale.location,
        qty=qty,
        unit=unit,
        unit_price=unit_price,
        discount_amount=discount,
        tax_rate=tax_rate,
        line_total=line_total,
    )
    _recalculate_sale_totals(sale)
    sale.refresh_from_db()

    return JsonResponse({
        'line_id': line.pk,
        'item_code': item.code,
        'item_name': item.name,
        'qty': str(qty),
        'unit_price': str(unit_price),
        'line_total': str(line_total),
        'subtotal': str(sale.subtotal),
        'discount_total': str(sale.discount_total),
        'tax_total': str(sale.tax_total),
        'grand_total': str(sale.grand_total),
    })


@login_required
@require_POST
def terminal_remove_line(request, line_id):
    """Remove a line from a DRAFT sale."""
    line = get_object_or_404(POSSaleLine, pk=line_id)
    sale = line.sale
    if sale.status != SaleStatus.DRAFT:
        return JsonResponse({'error': 'Sale is not in DRAFT.'}, status=400)

    line.delete()
    _recalculate_sale_totals(sale)
    sale.refresh_from_db()
    return JsonResponse({
        'subtotal': str(sale.subtotal),
        'discount_total': str(sale.discount_total),
        'tax_total': str(sale.tax_total),
        'grand_total': str(sale.grand_total),
    })


@login_required
@require_POST
def terminal_update_qty(request, line_id):
    """Update qty on a DRAFT sale line (AJAX endpoint for +/- buttons)."""
    line = get_object_or_404(POSSaleLine, pk=line_id)
    sale = line.sale
    if sale.status != SaleStatus.DRAFT:
        return JsonResponse({'error': 'Sale is not in DRAFT.'}, status=400)

    new_qty = Decimal(request.POST.get('qty', '1'))
    if new_qty < 1:
        new_qty = Decimal('1')

    # Allow dynamic repricing from frontend
    new_unit_price = request.POST.get('new_unit_price')
    if new_unit_price:
        line.unit_price = Decimal(new_unit_price)

    line_subtotal = new_qty * line.unit_price - line.discount_amount
    tax_amount = line_subtotal * line.tax_rate / 100
    line.qty = new_qty
    line.line_total = line_subtotal + tax_amount
    line.save(update_fields=['qty', 'unit_price', 'line_total'])

    _recalculate_sale_totals(sale)
    sale.refresh_from_db()
    return JsonResponse({
        'line_id': line.pk,
        'qty': str(line.qty),
        'unit_price': str(line.unit_price),
        'line_total': str(line.line_total),
        'subtotal': str(sale.subtotal),
        'discount_total': str(sale.discount_total),
        'tax_total': str(sale.tax_total),
        'grand_total': str(sale.grand_total),
    })


@login_required
@require_POST
def terminal_checkout(request, sale_id):
    """Complete checkout: set payments, mark paid, post sale."""
    sale = get_object_or_404(POSSale, pk=sale_id)
    if sale.status != SaleStatus.DRAFT:
        return JsonResponse({'error': 'Sale is not in DRAFT.'}, status=400)

    import json
    try:
        payments_data = json.loads(request.POST.get('payments', '[]'))
    except (json.JSONDecodeError, TypeError):
        payments_data = []

    if not payments_data:
        # Default to cash for full amount
        payments_data = [{'method': 'CASH', 'amount': str(sale.grand_total)}]

    # Create payments
    sale.payments.all().delete()
    for p in payments_data:
        POSPayment.objects.create(
            sale=sale,
            method=p.get('method', 'CASH'),
            amount=Decimal(str(p['amount'])),
            reference_no=p.get('reference_no', ''),
        )

    # Mark paid
    payment_sum = sum(p.amount for p in sale.payments.all())
    if payment_sum < sale.grand_total:
        return JsonResponse({
            'error': f'Payment total ({payment_sum}) < grand total ({sale.grand_total}).'
        }, status=400)

    sale.status = SaleStatus.PAID
    sale.save(update_fields=['status', 'updated_at'])

    # Post (deduct stock)
    try:
        post_pos_sale(sale.pk, request.user)
        sale.refresh_from_db()
        return JsonResponse({
            'status': 'posted',
            'sale_no': sale.sale_no,
            'sale_id': sale.pk,
            'grand_total': str(sale.grand_total),
            'change': str(payment_sum - sale.grand_total),
        })
    except ValueError as e:
        # Revert to DRAFT on stock error
        sale.status = SaleStatus.DRAFT
        sale.save(update_fields=['status', 'updated_at'])
        return JsonResponse({'error': str(e)}, status=400)
