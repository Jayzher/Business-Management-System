from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.utils import timezone

from services.models import CustomerService, ServiceLine, ServiceStatus
from services.forms import CustomerServiceForm, CustomerServiceEditForm, ServiceLineFormSet


# ═══════════════════════════════════════════════════════════════════════════
# LIST
# ═══════════════════════════════════════════════════════════════════════════
@login_required
def service_list(request):
    status_filter = request.GET.get('status', '')
    qs = CustomerService.objects.select_related('created_by', 'invoice')
    if status_filter:
        qs = qs.filter(status=status_filter)
    return render(request, 'services/service_list.html', {
        'services': qs,
        'status_filter': status_filter,
        'statuses': ServiceStatus.choices,
    })


# ═══════════════════════════════════════════════════════════════════════════
# DETAIL
# ═══════════════════════════════════════════════════════════════════════════
@login_required
def service_detail(request, pk):
    svc = get_object_or_404(
        CustomerService.objects.prefetch_related('lines__item', 'lines__unit', 'lines__location'),
        pk=pk,
    )
    return render(request, 'services/service_detail.html', {'service': svc})


# ═══════════════════════════════════════════════════════════════════════════
# CREATE
# ═══════════════════════════════════════════════════════════════════════════
@login_required
def service_create(request):
    if request.method == 'POST':
        form = CustomerServiceForm(request.POST)
        formset = ServiceLineFormSet(request.POST, prefix='lines')
        if form.is_valid():
            svc = form.save(commit=False)
            svc.created_by = request.user
            svc.save()
            formset = ServiceLineFormSet(request.POST, instance=svc, prefix='lines')
            if formset.is_valid():
                formset.save()
                messages.success(request, f'Service {svc.service_number} created.')
                return redirect('service_detail', pk=svc.pk)
    else:
        form = CustomerServiceForm()
        formset = ServiceLineFormSet(prefix='lines')
    return render(request, 'services/service_form.html', {
        'form': form,
        'formset': formset,
        'title': 'New Customer Service',
        'is_create': True,
    })


# ═══════════════════════════════════════════════════════════════════════════
# EDIT
# ═══════════════════════════════════════════════════════════════════════════
@login_required
def service_edit(request, pk):
    svc = get_object_or_404(CustomerService, pk=pk)
    if svc.status in (ServiceStatus.COMPLETED, ServiceStatus.CANCELLED):
        messages.error(request, 'Cannot edit a Completed or Cancelled service.')
        return redirect('service_detail', pk=pk)
    if request.method == 'POST':
        form = CustomerServiceEditForm(request.POST, instance=svc)
        formset = ServiceLineFormSet(request.POST, instance=svc, prefix='lines')
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            messages.success(request, f'Service {svc.service_number} updated.')
            return redirect('service_detail', pk=svc.pk)
    else:
        form = CustomerServiceEditForm(instance=svc)
        formset = ServiceLineFormSet(instance=svc, prefix='lines')
    return render(request, 'services/service_form.html', {
        'form': form,
        'formset': formset,
        'title': f'Edit Service: {svc.service_number}',
        'service': svc,
        'is_create': False,
    })


# ═══════════════════════════════════════════════════════════════════════════
# DELETE
# ═══════════════════════════════════════════════════════════════════════════
@login_required
def service_delete(request, pk):
    svc = get_object_or_404(CustomerService, pk=pk)
    if svc.status == ServiceStatus.COMPLETED:
        messages.error(request, 'Cannot delete a Completed service.')
        return redirect('service_detail', pk=pk)
    if request.method == 'POST':
        svc.delete()
        messages.success(request, 'Service deleted.')
        return redirect('service_list')
    return render(request, 'services/service_delete.html', {'service': svc})


# ═══════════════════════════════════════════════════════════════════════════
# MARK IN-PROGRESS
# ═══════════════════════════════════════════════════════════════════════════
@login_required
def service_start(request, pk):
    svc = get_object_or_404(CustomerService, pk=pk)
    if request.method == 'POST':
        if svc.status == ServiceStatus.DRAFT:
            svc.status = ServiceStatus.IN_PROGRESS
            svc.save(update_fields=['status', 'updated_at'])
            messages.success(request, f'Service {svc.service_number} marked as In Progress.')
        else:
            messages.error(request, 'Only DRAFT services can be started.')
    return redirect('service_detail', pk=pk)


# ═══════════════════════════════════════════════════════════════════════════
# COMPLETE — deducts inventory + generates invoice
# ═══════════════════════════════════════════════════════════════════════════
@login_required
@transaction.atomic
def service_complete(request, pk):
    svc = get_object_or_404(CustomerService, pk=pk)
    if request.method != 'POST':
        return redirect('service_detail', pk=pk)

    if svc.status not in (ServiceStatus.DRAFT, ServiceStatus.IN_PROGRESS):
        messages.error(request, 'Only Draft or In Progress services can be completed.')
        return redirect('service_detail', pk=pk)

    now = timezone.now()
    lines = list(svc.lines.select_related('item', 'unit', 'location').all())

    # ── Inventory deduction ────────────────────────────────────────────────
    if lines:
        try:
            from inventory.models import StockMove, StockBalance, MoveType, MoveStatus
            moves = []
            for line in lines:
                if line.location is None:
                    continue
                move = StockMove(
                    move_type=MoveType.DELIVER,
                    item=line.item,
                    qty=line.qty,
                    unit=line.unit,
                    from_location=line.location,
                    to_location=None,
                    reference_type='CustomerService',
                    reference_id=svc.pk,
                    reference_number=svc.service_number,
                    batch_number='',
                    serial_number='',
                    status=MoveStatus.POSTED,
                    created_by=request.user,
                    posted_by=request.user,
                    posted_at=now,
                )
                moves.append(move)

                # Deduct stock balance
                balance, _ = StockBalance.objects.select_for_update().get_or_create(
                    item=line.item,
                    location=line.location,
                    defaults={'qty_on_hand': Decimal('0'), 'qty_reserved': Decimal('0')},
                )
                balance.qty_on_hand -= line.qty
                wh = line.location.warehouse
                if not wh.allow_negative_stock and balance.qty_on_hand < 0:
                    raise ValueError(
                        f"Insufficient stock for {line.item.code} at {line.location}. "
                        f"Available: {balance.qty_on_hand + line.qty}, Requested: {line.qty}"
                    )
                balance.save()

            if moves:
                StockMove.objects.bulk_create(moves)

        except ValueError as exc:
            messages.error(request, f'Stock error: {exc}')
            return redirect('service_detail', pk=pk)

    # ── Generate Invoice ───────────────────────────────────────────────────
    from core.models import Invoice, InvoiceLine
    from core.views import _next_invoice_number

    grand_total = svc.grand_total or Decimal('0')

    inv = Invoice.objects.create(
        invoice_number=_next_invoice_number(),
        date=now.date(),
        customer_name=svc.customer_name,
        customer_address=svc.address,
        subtotal=grand_total,
        grand_total=grand_total,
        notes=f'Service: {svc.service_name}',
        created_by=request.user,
    )

    if lines:
        for line in lines:
            InvoiceLine.objects.create(
                invoice=inv,
                item_code=line.item.code,
                item_name=line.item.name,
                qty=line.qty,
                unit=line.unit.abbreviation,
                unit_price=line.unit_price,
                line_total=line.line_total,
            )
    else:
        # No lines — create single summary line
        InvoiceLine.objects.create(
            invoice=inv,
            item_code='SVC',
            item_name=svc.service_name,
            qty=Decimal('1'),
            unit='svc',
            unit_price=grand_total,
            line_total=grand_total,
        )

    # ── Mark service completed ─────────────────────────────────────────────
    svc.status = ServiceStatus.COMPLETED
    svc.invoice = inv
    svc.posted_by = request.user
    svc.posted_at = now
    if not svc.completion_date:
        svc.completion_date = now.date()
    svc.save(update_fields=[
        'status', 'invoice', 'posted_by', 'posted_at',
        'completion_date', 'updated_at',
    ])

    messages.success(
        request,
        f'Service {svc.service_number} completed. Invoice {inv.invoice_number} generated.'
    )
    return redirect('service_detail', pk=pk)


# ═══════════════════════════════════════════════════════════════════════════
# CANCEL
# ═══════════════════════════════════════════════════════════════════════════
@login_required
def service_cancel(request, pk):
    svc = get_object_or_404(CustomerService, pk=pk)
    if request.method == 'POST':
        if svc.status in (ServiceStatus.DRAFT, ServiceStatus.IN_PROGRESS):
            svc.status = ServiceStatus.CANCELLED
            svc.save(update_fields=['status', 'updated_at'])
            messages.success(request, f'Service {svc.service_number} cancelled.')
        else:
            messages.error(request, 'Cannot cancel a Completed service.')
    return redirect('service_detail', pk=pk)
