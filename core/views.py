from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum, Q, F, DecimalField
from django.db.models.functions import Coalesce, TruncMonth, TruncDate
from django.utils import timezone
from django.http import HttpResponse
from datetime import timedelta

from core.models import (
    BusinessProfile, SalesChannel, ExpenseCategory, Expense,
    Invoice, InvoiceLine, SupplyCategory, SupplyItem, SupplyMovement,
    TargetGoal,
)
from core.forms import (
    BusinessProfileForm, SalesChannelForm, ExpenseCategoryForm, ExpenseForm,
    SupplyCategoryForm, SupplyItemForm, SupplyMovementForm, TargetGoalForm,
)
from core.cogs import compute_invoice_cogs
from accounts.decorators import write_denied_for_viewer


# ═══════════════════════════════════════════════════════════════════════════
# SETTINGS / BUSINESS PROFILE
# ═══════════════════════════════════════════════════════════════════════════
@login_required
@write_denied_for_viewer
def settings_view(request):
    profile = BusinessProfile.get_instance()
    if request.method == 'POST':
        form = BusinessProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, 'Business profile updated.')
            return redirect('settings')
    else:
        form = BusinessProfileForm(instance=profile)
    return render(request, 'core/settings.html', {'form': form, 'profile': profile})


# ═══════════════════════════════════════════════════════════════════════════
# SALES CHANNELS
# ═══════════════════════════════════════════════════════════════════════════
@login_required
def channel_list(request):
    channels = SalesChannel.objects.all()
    return render(request, 'core/channel_list.html', {'channels': channels})


@login_required
@write_denied_for_viewer
def channel_create(request):
    if request.method == 'POST':
        form = SalesChannelForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Sales channel created.')
            return redirect('channel_list')
    else:
        form = SalesChannelForm()
    return render(request, 'core/channel_form.html', {'form': form, 'title': 'New Sales Channel'})


@login_required
@write_denied_for_viewer
def channel_edit(request, pk):
    obj = get_object_or_404(SalesChannel, pk=pk)
    if request.method == 'POST':
        form = SalesChannelForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, 'Sales channel updated.')
            return redirect('channel_list')
    else:
        form = SalesChannelForm(instance=obj)
    return render(request, 'core/channel_form.html', {'form': form, 'title': f'Edit: {obj.name}'})


@login_required
@write_denied_for_viewer
def channel_delete(request, pk):
    obj = get_object_or_404(SalesChannel, pk=pk)
    if request.method == 'POST':
        obj.soft_delete()
        messages.success(request, 'Sales channel deleted.')
        return redirect('channel_list')
    return render(request, 'core/confirm_delete.html', {'object': obj, 'cancel_url': 'channel_list'})


# ═══════════════════════════════════════════════════════════════════════════
# EXPENSE CATEGORIES
# ═══════════════════════════════════════════════════════════════════════════
@login_required
def expense_category_list(request):
    categories = ExpenseCategory.objects.all()
    return render(request, 'core/expense_category_list.html', {'categories': categories})


@login_required
@write_denied_for_viewer
def expense_category_create(request):
    if request.method == 'POST':
        form = ExpenseCategoryForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Expense category created.')
            return redirect('expense_category_list')
    else:
        form = ExpenseCategoryForm()
    return render(request, 'core/expense_category_form.html', {'form': form, 'title': 'New Expense Category'})


@login_required
@write_denied_for_viewer
def expense_category_edit(request, pk):
    obj = get_object_or_404(ExpenseCategory, pk=pk)
    if request.method == 'POST':
        form = ExpenseCategoryForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, 'Expense category updated.')
            return redirect('expense_category_list')
    else:
        form = ExpenseCategoryForm(instance=obj)
    return render(request, 'core/expense_category_form.html', {'form': form, 'title': f'Edit: {obj.name}'})


@login_required
@write_denied_for_viewer
def expense_category_delete(request, pk):
    obj = get_object_or_404(ExpenseCategory, pk=pk)
    if request.method == 'POST':
        obj.soft_delete()
        messages.success(request, 'Expense category deleted.')
        return redirect('expense_category_list')
    return render(request, 'core/confirm_delete.html', {'object': obj, 'cancel_url': 'expense_category_list'})


# ═══════════════════════════════════════════════════════════════════════════
# EXPENSES  (Expense Listing)
# ═══════════════════════════════════════════════════════════════════════════
@login_required
def expense_list(request):
    qs = Expense.objects.select_related('category', 'created_by')
    cat = request.GET.get('category')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    if cat:
        qs = qs.filter(category_id=cat)
    if date_from:
        qs = qs.filter(date__gte=date_from)
    if date_to:
        qs = qs.filter(date__lte=date_to)
    total = qs.aggregate(total=Coalesce(Sum('amount'), Decimal('0'), output_field=DecimalField()))['total']
    categories = ExpenseCategory.objects.all()
    return render(request, 'core/expense_list.html', {
        'expenses': qs[:500],
        'categories': categories,
        'total': total,
        'filters': {'category': cat or '', 'date_from': date_from or '', 'date_to': date_to or ''},
    })


@login_required
@write_denied_for_viewer
def expense_create(request):
    if request.method == 'POST':
        form = ExpenseForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.created_by = request.user
            obj.save()
            messages.success(request, 'Expense recorded.')
            return redirect('expense_list')
    else:
        form = ExpenseForm(initial={'date': timezone.now().date()})
    return render(request, 'core/expense_form.html', {'form': form, 'title': 'Record Expense'})


@login_required
@write_denied_for_viewer
def expense_edit(request, pk):
    obj = get_object_or_404(Expense, pk=pk)
    if request.method == 'POST':
        form = ExpenseForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, 'Expense updated.')
            return redirect('expense_list')
    else:
        form = ExpenseForm(instance=obj)
    return render(request, 'core/expense_form.html', {'form': form, 'title': 'Edit Expense'})


@login_required
@write_denied_for_viewer
def expense_delete(request, pk):
    obj = get_object_or_404(Expense, pk=pk)
    if request.method == 'POST':
        obj.delete()
        messages.success(request, 'Expense deleted.')
        return redirect('expense_list')
    return render(request, 'core/confirm_delete.html', {'object': obj, 'cancel_url': 'expense_list'})


# ═══════════════════════════════════════════════════════════════════════════
# INVOICE GENERATOR
# ═══════════════════════════════════════════════════════════════════════════
def _next_invoice_number():
    last = Invoice.objects.order_by('-id').first()
    num = (last.id + 1) if last else 1
    return f"{num:06d}"

def _compute_cogs_for_invoice(inv):
    """Compute COGS from linked source document and save to grand_total_cogs."""
    cogs = compute_invoice_cogs(inv)
    if inv.grand_total_cogs != cogs:
        inv.grand_total_cogs = cogs
        inv.save(update_fields=['grand_total_cogs'])
    return cogs

@login_required
def invoice_list(request):
    from django.db.models import Sum, Count, DecimalField
    from django.db.models.functions import Coalesce
    from decimal import Decimal
    # Exclude invoices that belong to a CustomerService (those live in services/)
    service_invoice_ids = Invoice.objects.filter(
        customer_services__isnull=False
    ).values_list('id', flat=True)
    invoices = Invoice.objects.exclude(
        pk__in=service_invoice_ids
    ).select_related('created_by')[:200]
    invoice_summary = Invoice.objects.exclude(
        pk__in=service_invoice_ids
    ).aggregate(
        count=Count('id'),
        total=Coalesce(Sum('grand_total'), Decimal('0'), output_field=DecimalField()),
    )
    return render(request, 'core/invoice_list.html', {
        'invoices': invoices,
        'invoice_summary': invoice_summary,
    })


@login_required
@write_denied_for_viewer
def invoice_from_sale(request, sale_id):
    """Generate invoice from a POS Sale."""
    from pos.models import POSSale
    sale = get_object_or_404(POSSale, pk=sale_id)

    # Check if invoice already exists
    existing = Invoice.objects.filter(pos_sale=sale).first()
    if existing:
        return redirect('invoice_detail', pk=existing.pk)

    profile = BusinessProfile.get_instance()
    is_paid = sale.status in ('PAID', 'POSTED')
    today = timezone.now().date()
    inv = Invoice.objects.create(
        invoice_number=_next_invoice_number(),
        date=today,
        pos_sale=sale,
        customer_name=sale.customer.name if sale.customer else 'Walk-in Customer',
        customer_address=sale.customer.address if sale.customer else '',
        subtotal=sale.subtotal,
        discount_total=sale.discount_total,
        tax_total=sale.tax_total,
        grand_total=sale.grand_total,
        is_paid=is_paid,
        paid_at=timezone.now() if is_paid else None,
        paid_date=today if is_paid else None,
        created_by=request.user,
    )
    for line in sale.lines.select_related('item', 'unit'):
        InvoiceLine.objects.create(
            invoice=inv,
            item_code=line.item.code,
            item_name=line.item.name,
            qty=line.qty,
            unit=line.unit.abbreviation,
            unit_price=line.unit_price,
            discount=line.discount_amount,
            line_total=line.line_total,
        )
    if is_paid:
        _compute_cogs_for_invoice(inv)
        from core.models import InvoicePayment, PaymentMethod as PM
        if not inv.payments.exists():
            InvoicePayment.objects.create(
                invoice=inv,
                date=today,
                method=PM.CASH,
                amount=inv.grand_total,
                reference_no=getattr(sale, 'sale_no', ''),
                notes='Auto-recorded from POS sale',
                created_by=request.user,
            )
    messages.success(request, f'Invoice {inv.invoice_number} generated.')
    return redirect('invoice_detail', pk=inv.pk)


@login_required
@write_denied_for_viewer
def invoice_from_so(request, so_id):
    """Generate invoice from a Sales Order."""
    from sales.models import SalesOrder
    so = get_object_or_404(SalesOrder, pk=so_id)

    existing = Invoice.objects.filter(sales_order=so).first()
    if existing:
        return redirect('invoice_detail', pk=existing.pk)

    lines_total = sum(l.line_total for l in so.lines.all())
    bundles_total = sum(b.bundle_total for b in so.price_list_lines.all())
    grand_total = lines_total + bundles_total

    inv = Invoice.objects.create(
        invoice_number=_next_invoice_number(),
        date=timezone.now().date(),
        sales_order=so,
        customer_name=so.customer.name if so.customer else '',
        customer_address=so.customer.address if so.customer else '',
        subtotal=lines_total,
        grand_total=grand_total,
        created_by=request.user,
    )
    for line in so.lines.select_related('item', 'unit'):
        InvoiceLine.objects.create(
            invoice=inv,
            item_code=line.item.code,
            item_name=line.item.name,
            qty=line.qty_ordered,
            unit=line.unit.abbreviation,
            unit_price=line.unit_price,
            line_total=line.line_total,
        )
    for bundle in so.price_list_lines.select_related('price_list').all():
        InvoiceLine.objects.create(
            invoice=inv,
            item_code='BUNDLE',
            item_name=bundle.price_list.name,
            qty=bundle.qty_multiplier,
            unit='bundle',
            unit_price=bundle.bundle_subtotal,
            line_total=bundle.bundle_total,
        )
    messages.success(request, f'Invoice {inv.invoice_number} generated.')
    return redirect('invoice_detail', pk=inv.pk)


@login_required
def invoice_detail(request, pk):
    inv = get_object_or_404(Invoice.objects.prefetch_related('lines', 'payments'), pk=pk)
    profile = BusinessProfile.get_instance()
    payments = list(inv.payments.order_by('date', 'created_at'))
    running = inv.grand_total
    payments_with_balance = []
    for p in payments:
        running -= p.amount
        p.balance_after = max(running, 0)
        payments_with_balance.append(p)
    total_paid = sum(p.amount for p in payments)
    balance_due = max(inv.grand_total - total_paid, 0)
    today_date = timezone.now().date()

    # Bundles (price list lines) attached to the linked Sales Order
    so_bundles = []
    if inv.sales_order_id:
        so_bundles = list(
            inv.sales_order.price_list_lines
            .select_related('price_list')
            .prefetch_related('price_list__items__item', 'price_list__items__unit')
            .all()
        )

    return render(request, 'core/invoice_detail.html', {
        'invoice': inv,
        'profile': profile,
        'total_paid': total_paid,
        'balance_due': balance_due,
        'payments_with_balance': payments_with_balance,
        'today_date': today_date,
        'so_bundles': so_bundles,
    })


@login_required
def invoice_print(request, pk):
    inv = get_object_or_404(Invoice.objects.prefetch_related('lines'), pk=pk)
    profile = BusinessProfile.get_instance()
    return render(request, 'core/invoice_print.html', {'invoice': inv, 'profile': profile})


@login_required
@write_denied_for_viewer
def invoice_add_payment(request, pk):
    """Add a payment to an invoice. If fully paid, mark invoice as paid and auto-post linked SO."""
    inv = get_object_or_404(Invoice, pk=pk)
    next_url = request.POST.get('next') or request.GET.get('next') or ''
    def _redirect():
        if next_url:
            return redirect(next_url)
        return redirect('invoice_detail', pk=pk)
    if request.method == 'POST':
        from core.models import InvoicePayment, PaymentMethod as PM
        from decimal import Decimal
        amount = Decimal(request.POST.get('amount', '0'))
        method = request.POST.get('method', PM.CASH)
        reference_no = request.POST.get('reference_no', '')
        notes = request.POST.get('notes', '')

        if amount <= 0:
            messages.error(request, 'Payment amount must be greater than 0.')
            return redirect('invoice_detail', pk=pk)

        existing_paid = sum(p.amount for p in inv.payments.all())
        balance_due = max(inv.grand_total - existing_paid, Decimal('0'))
        if balance_due <= 0:
            messages.error(request, 'Invoice has no outstanding balance — it is already fully paid.')
            return redirect('invoice_detail', pk=pk)
        if amount > balance_due:
            messages.error(
                request,
                f'Payment of ₱{amount:,.2f} exceeds the balance due of ₱{balance_due:,.2f}. '
                'Please enter an amount equal to or less than the outstanding balance.'
            )
            return redirect('invoice_detail', pk=pk)

        payment_date_str = request.POST.get('payment_date', '') or timezone.now().date().isoformat()
        try:
            from datetime import date as _date
            payment_date = _date.fromisoformat(payment_date_str)
        except (ValueError, TypeError):
            payment_date = timezone.now().date()

        InvoicePayment.objects.create(
            invoice=inv,
            date=payment_date,
            method=method,
            amount=amount,
            reference_no=reference_no,
            notes=notes,
            created_by=request.user,
        )
        messages.success(request, f'Payment of \u20b1{amount:,.2f} recorded.')

        # Check if fully paid
        total_paid = sum(p.amount for p in inv.payments.all())
        if total_paid >= inv.grand_total and not inv.is_paid:
            inv.is_paid = True
            inv.paid_at = timezone.now()
            inv.paid_date = payment_date
            inv.save(update_fields=['is_paid', 'paid_at', 'paid_date', 'updated_at'])
            _compute_cogs_for_invoice(inv)
            messages.success(request, f'Invoice {inv.invoice_number} fully paid — marked PAID.')

            # Auto-post linked Sales Order if it exists and is APPROVED
            if inv.sales_order:
                so = inv.sales_order
                from core.models import DocumentStatus
                if so.status == DocumentStatus.APPROVED:
                    so.status = DocumentStatus.POSTED
                    so.posted_by = request.user
                    so.posted_at = timezone.now()
                    so.save(update_fields=['status', 'posted_by', 'posted_at', 'updated_at'])
                    messages.info(request, f'Sales Order {so.document_number} auto-posted (invoice paid).')

    return _redirect()


@login_required
@write_denied_for_viewer
def invoice_mark_paid(request, pk):
    """Manually mark an invoice as fully paid (records a single full-amount payment if none exist)."""
    inv = get_object_or_404(Invoice, pk=pk)
    next_url = request.POST.get('next') or request.GET.get('next') or ''
    if request.method == 'POST':
        if not inv.is_paid:
            from core.models import InvoicePayment, PaymentMethod as PM
            from decimal import Decimal
            today = timezone.now().date()
            existing_paid = sum(p.amount for p in inv.payments.all())
            remaining = inv.grand_total - existing_paid
            if remaining > 0:
                InvoicePayment.objects.create(
                    invoice=inv,
                    date=today,
                    method=PM.CASH,
                    amount=remaining,
                    reference_no='',
                    notes='Marked paid manually',
                    created_by=request.user,
                )
            inv.is_paid = True
            inv.paid_at = timezone.now()
            inv.paid_date = today
            inv.save(update_fields=['is_paid', 'paid_at', 'paid_date', 'updated_at'])
            _compute_cogs_for_invoice(inv)
            messages.success(request, f'Invoice {inv.invoice_number} marked as PAID.')

            if inv.sales_order:
                so = inv.sales_order
                from core.models import DocumentStatus
                if so.status == DocumentStatus.APPROVED:
                    so.status = DocumentStatus.POSTED
                    so.posted_by = request.user
                    so.posted_at = timezone.now()
                    so.save(update_fields=['status', 'posted_by', 'posted_at', 'updated_at'])
                    messages.info(request, f'Sales Order {so.document_number} auto-posted.')
        else:
            messages.info(request, 'Invoice is already paid.')
    if next_url:
        return redirect(next_url)
    return redirect('invoice_detail', pk=pk)


@login_required
@write_denied_for_viewer
def invoice_delete_payment(request, pk, payment_pk):
    """Delete a single payment record from an invoice (re-opens invoice if was paid)."""
    inv = get_object_or_404(Invoice, pk=pk)
    next_url = request.POST.get('next') or request.GET.get('next') or ''
    from core.models import InvoicePayment
    payment = get_object_or_404(InvoicePayment, pk=payment_pk, invoice=inv)
    if request.method == 'POST':
        payment.delete()
        messages.success(request, 'Payment record deleted.')
        total_paid = sum(p.amount for p in inv.payments.all())
        if inv.is_paid and total_paid < inv.grand_total:
            inv.is_paid = False
            inv.paid_at = None
            inv.paid_date = None
            inv.save(update_fields=['is_paid', 'paid_at', 'paid_date', 'updated_at'])
            messages.warning(request, 'Invoice re-opened (total payments now below grand total).')
    if next_url:
        return redirect(next_url)
    return redirect('invoice_detail', pk=pk)


# ═══════════════════════════════════════════════════════════════════════════
# SUPPLIES INVENTORY
# ═══════════════════════════════════════════════════════════════════════════
@login_required
def supply_item_list(request):
    items = SupplyItem.objects.select_related('category')
    return render(request, 'core/supply_item_list.html', {'items': items})


@login_required
@write_denied_for_viewer
def supply_item_create(request):
    if request.method == 'POST':
        form = SupplyItemForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Supply item created.')
            return redirect('supply_item_list')
    else:
        form = SupplyItemForm()
    return render(request, 'core/supply_item_form.html', {'form': form, 'title': 'New Supply Item'})


@login_required
@write_denied_for_viewer
def supply_item_edit(request, pk):
    obj = get_object_or_404(SupplyItem, pk=pk)
    if request.method == 'POST':
        form = SupplyItemForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, 'Supply item updated.')
            return redirect('supply_item_list')
    else:
        form = SupplyItemForm(instance=obj)
    return render(request, 'core/supply_item_form.html', {'form': form, 'title': f'Edit: {obj.name}'})


@login_required
@write_denied_for_viewer
def supply_item_delete(request, pk):
    obj = get_object_or_404(SupplyItem, pk=pk)
    if request.method == 'POST':
        obj.soft_delete()
        messages.success(request, 'Supply item deleted.')
        return redirect('supply_item_list')
    return render(request, 'core/confirm_delete.html', {'object': obj, 'cancel_url': 'supply_item_list'})


@login_required
def supply_movement_list(request):
    qs = SupplyMovement.objects.select_related('supply_item', 'created_by')
    item_id = request.GET.get('item')
    mtype = request.GET.get('type')
    if item_id:
        qs = qs.filter(supply_item_id=item_id)
    if mtype:
        qs = qs.filter(movement_type=mtype)
    items = SupplyItem.objects.all()
    return render(request, 'core/supply_movement_list.html', {
        'movements': qs[:500], 'items': items,
        'filters': {'item': item_id or '', 'type': mtype or ''},
    })


@login_required
@write_denied_for_viewer
def supply_movement_create(request):
    if request.method == 'POST':
        form = SupplyMovementForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.created_by = request.user
            obj.save()
            messages.success(request, 'Supply movement recorded.')
            return redirect('supply_movement_list')
    else:
        form = SupplyMovementForm(initial={'date': timezone.now().date()})
    return render(request, 'core/supply_movement_form.html', {'form': form, 'title': 'Record Supply Movement'})


@login_required
def supply_category_list(request):
    cats = SupplyCategory.objects.all()
    return render(request, 'core/supply_category_list.html', {'categories': cats})


@login_required
@write_denied_for_viewer
def supply_category_create(request):
    if request.method == 'POST':
        form = SupplyCategoryForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Supply category created.')
            return redirect('supply_category_list')
    else:
        form = SupplyCategoryForm()
    return render(request, 'core/supply_category_form.html', {'form': form, 'title': 'New Supply Category'})


@login_required
@write_denied_for_viewer
def supply_category_edit(request, pk):
    obj = get_object_or_404(SupplyCategory, pk=pk)
    if request.method == 'POST':
        form = SupplyCategoryForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, 'Supply category updated.')
            return redirect('supply_category_list')
    else:
        form = SupplyCategoryForm(instance=obj)
    return render(request, 'core/supply_category_form.html', {'form': form, 'title': f'Edit: {obj.name}'})


@login_required
@write_denied_for_viewer
def supply_category_delete(request, pk):
    obj = get_object_or_404(SupplyCategory, pk=pk)
    if request.method == 'POST':
        obj.soft_delete()
        messages.success(request, 'Supply category deleted.')
        return redirect('supply_category_list')
    return render(request, 'core/confirm_delete.html', {'object': obj, 'cancel_url': 'supply_category_list'})


# ═══════════════════════════════════════════════════════════════════════════
# TARGET GOALS
# ═══════════════════════════════════════════════════════════════════════════
@login_required
def goal_list(request):
    qs = TargetGoal.objects.select_related('assigned_to', 'created_by')
    status = request.GET.get('status')
    if status:
        qs = qs.filter(status=status)
    return render(request, 'core/goal_list.html', {
        'goals': qs,
        'filter_status': status or '',
    })


@login_required
@write_denied_for_viewer
def goal_create(request):
    if request.method == 'POST':
        form = TargetGoalForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.created_by = request.user
            obj.save()
            messages.success(request, 'Goal created.')
            return redirect('goal_list')
    else:
        form = TargetGoalForm()
    return render(request, 'core/goal_form.html', {'form': form, 'title': 'New Goal'})


@login_required
@write_denied_for_viewer
def goal_edit(request, pk):
    obj = get_object_or_404(TargetGoal, pk=pk)
    if request.method == 'POST':
        form = TargetGoalForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, 'Goal updated.')
            return redirect('goal_list')
    else:
        form = TargetGoalForm(instance=obj)
    return render(request, 'core/goal_form.html', {'form': form, 'title': f'Edit: {obj.title}'})


@login_required
@write_denied_for_viewer
def goal_delete(request, pk):
    obj = get_object_or_404(TargetGoal, pk=pk)
    if request.method == 'POST':
        obj.delete()
        messages.success(request, 'Goal deleted.')
        return redirect('goal_list')
    return render(request, 'core/confirm_delete.html', {'object': obj, 'cancel_url': 'goal_list'})


# ═══════════════════════════════════════════════════════════════════════════
# DICTIONARY
# ═══════════════════════════════════════════════════════════════════════════
@login_required
def dictionary_view(request):
    return render(request, 'core/dictionary.html')


# ═══════════════════════════════════════════════════════════════════════════
# TESTS & SYNCS  (Admin only)
# ═══════════════════════════════════════════════════════════════════════════
import io
import json as _json
from django.http import JsonResponse
from accounts.decorators import admin_required


# Registry of runnable actions --------------------------------------------------
_SYNC_ACTIONS = {
    'seed_roles': {
        'label': 'Seed Roles',
        'icon': 'fas fa-user-shield',
        'color': 'primary',
        'description': 'Create the 7 default system roles if they do not exist yet.',
        'category': 'seed',
        'command': 'seed_roles',
        'args': [],
    },
    'seed_units': {
        'label': 'Seed Units',
        'icon': 'fas fa-ruler-combined',
        'color': 'primary',
        'description': 'Create or update standard units of measure and common conversions.',
        'category': 'seed',
        'command': 'seed_units',
        'args': [],
    },
    'seed_data': {
        'label': 'Seed Sample Data',
        'icon': 'fas fa-database',
        'color': 'secondary',
        'description': 'Load sample categories, warehouse, partners, and items (idempotent).',
        'category': 'seed',
        'command': 'seed_data',
        'args': [],
    },
    'backfill_selling_units': {
        'label': 'Backfill Selling Units',
        'icon': 'fas fa-exchange-alt',
        'color': 'info',
        'description': 'Set selling_unit = default_unit for items where selling_unit is blank.',
        'category': 'sync',
        'command': 'backfill_item_selling_units',
        'args': [],
    },
    'sync_invoice_cogs': {
        'label': 'Sync Invoice COGS',
        'icon': 'fas fa-calculator',
        'color': 'warning',
        'description': 'Recompute grand_total_cogs on all Invoice records from source documents.',
        'category': 'sync',
        'command': 'sync_invoice_cogs',
        'args': [],
    },
    'sync_payments': {
        'label': 'Sync Payments',
        'icon': 'fas fa-money-check-alt',
        'color': 'warning',
        'description': 'Backfill missing InvoicePayment records and paid_date for paid invoices.',
        'category': 'sync',
        'command': 'sync_payments',
        'args': ['--cogs'],
    },
    'sync_pos_stock': {
        'label': 'Sync POS Stock Moves',
        'icon': 'fas fa-cash-register',
        'color': 'warning',
        'description': 'Backfill missing StockMove rows for completed POS receipts.',
        'category': 'sync',
        'command': 'sync_pos_stock_moves',
        'args': [],
    },
    'resync_inventory': {
        'label': 'Full Inventory Resync',
        'icon': 'fas fa-sync-alt',
        'color': 'danger',
        'description': 'Phase 0-3: deduplicate moves, fix quantities, rebuild StockBalance from all posted documents, run integrity audit. This may take a while.',
        'category': 'sync',
        'command': 'resync_inventory',
        'args': ['--quiet'],
    },
    'resync_inventory_dry': {
        'label': 'Inventory Resync (Dry Run)',
        'icon': 'fas fa-search',
        'color': 'info',
        'description': 'Preview what the full inventory resync would change without writing to the database.',
        'category': 'test',
        'command': 'resync_inventory',
        'args': ['--dry-run', '--quiet'],
    },
    'integrity_audit': {
        'label': 'Integrity Audit',
        'icon': 'fas fa-stethoscope',
        'color': 'info',
        'description': 'Run Phase 3 only: check for negative balances, duplicate moves, unknown reference types, missing unit conversions.',
        'category': 'test',
        'command': 'resync_inventory',
        'args': ['--phase', '3'],
    },
    'django_check': {
        'label': 'Django System Check',
        'icon': 'fas fa-heartbeat',
        'color': 'success',
        'description': 'Run Django\'s built-in system check framework to detect common problems.',
        'category': 'test',
        'command': 'check',
        'args': [],
    },
}


def _gather_diagnostics():
    """Collect quick read-only stats for the dashboard cards."""
    from accounts.models import Role, UserRole, User
    from inventory.models import StockBalance, StockMove, MoveStatus
    from catalog.models import Item, Unit, UnitConversion, Category
    from warehouses.models import Warehouse, Location
    from core.models import Invoice

    total_users = User.objects.count()
    users_with_roles = UserRole.objects.values('user').distinct().count()
    roles = list(Role.objects.values_list('name', flat=True).order_by('name'))

    items_total = Item.objects.count()
    items_no_selling = Item.objects.filter(selling_unit__isnull=True).count()
    units_total = Unit.objects.count()
    conversions_total = UnitConversion.objects.count()
    categories_total = Category.objects.count()

    warehouses_total = Warehouse.objects.count()
    locations_total = Location.objects.count()

    balance_rows = StockBalance.objects.count()
    negative_balances = StockBalance.objects.filter(qty_on_hand__lt=0).count()
    move_total = StockMove.objects.filter(status=MoveStatus.POSTED).count()

    invoices_total = Invoice.objects.count()
    invoices_no_cogs = Invoice.objects.filter(is_paid=True, grand_total_cogs__isnull=True).count() + \
                       Invoice.objects.filter(is_paid=True, grand_total_cogs=0).count()
    invoices_no_payment = Invoice.objects.filter(is_paid=True).exclude(payments__isnull=False).count()

    return {
        'total_users': total_users,
        'users_with_roles': users_with_roles,
        'users_no_roles': total_users - users_with_roles,
        'roles': roles,
        'items_total': items_total,
        'items_no_selling': items_no_selling,
        'units_total': units_total,
        'conversions_total': conversions_total,
        'categories_total': categories_total,
        'warehouses_total': warehouses_total,
        'locations_total': locations_total,
        'balance_rows': balance_rows,
        'negative_balances': negative_balances,
        'move_total': move_total,
        'invoices_total': invoices_total,
        'invoices_no_cogs': invoices_no_cogs,
        'invoices_no_payment': invoices_no_payment,
    }


@login_required
@admin_required
def tests_syncs_view(request):
    """Admin-only page: diagnostics dashboard + runnable sync/test actions."""
    diag = _gather_diagnostics()
    actions_by_cat = {}
    for key, action in _SYNC_ACTIONS.items():
        cat = action['category']
        actions_by_cat.setdefault(cat, []).append({**action, 'key': key})
    return render(request, 'core/tests_syncs.html', {
        'diag': diag,
        'seed_actions': actions_by_cat.get('seed', []),
        'sync_actions': actions_by_cat.get('sync', []),
        'test_actions': actions_by_cat.get('test', []),
    })


@login_required
@admin_required
def run_sync_action(request):
    """AJAX endpoint: run a management command and return its output."""
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'POST required'}, status=405)

    action_key = request.POST.get('action', '')
    spec = _SYNC_ACTIONS.get(action_key)
    if not spec:
        return JsonResponse({'ok': False, 'error': f'Unknown action: {action_key}'}, status=400)

    from django.core.management import call_command
    buf = io.StringIO()
    try:
        call_command(spec['command'], *spec['args'], stdout=buf, stderr=buf)
        output = buf.getvalue()
        return JsonResponse({'ok': True, 'output': output})
    except Exception as exc:
        output = buf.getvalue()
        return JsonResponse({'ok': False, 'output': output, 'error': str(exc)})
