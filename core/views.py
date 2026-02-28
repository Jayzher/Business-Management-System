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


# ═══════════════════════════════════════════════════════════════════════════
# SETTINGS / BUSINESS PROFILE
# ═══════════════════════════════════════════════════════════════════════════
@login_required
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


@login_required
def invoice_list(request):
    from django.db.models import Sum, Count, DecimalField
    from django.db.models.functions import Coalesce
    from decimal import Decimal
    invoices = Invoice.objects.select_related('created_by')[:200]
    invoice_summary = Invoice.objects.aggregate(
        count=Count('id'),
        total=Coalesce(Sum('grand_total'), Decimal('0'), output_field=DecimalField()),
    )
    return render(request, 'core/invoice_list.html', {
        'invoices': invoices,
        'invoice_summary': invoice_summary,
    })


@login_required
def invoice_from_sale(request, sale_id):
    """Generate invoice from a POS Sale."""
    from pos.models import POSSale
    sale = get_object_or_404(POSSale, pk=sale_id)

    # Check if invoice already exists
    existing = Invoice.objects.filter(pos_sale=sale).first()
    if existing:
        return redirect('invoice_detail', pk=existing.pk)

    profile = BusinessProfile.get_instance()
    inv = Invoice.objects.create(
        invoice_number=_next_invoice_number(),
        date=timezone.now().date(),
        pos_sale=sale,
        customer_name=sale.customer.name if sale.customer else 'Walk-in Customer',
        customer_address=sale.customer.address if sale.customer else '',
        subtotal=sale.subtotal,
        discount_total=sale.discount_total,
        tax_total=sale.tax_total,
        grand_total=sale.grand_total,
        is_paid=sale.status in ('PAID', 'POSTED'),
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
    messages.success(request, f'Invoice {inv.invoice_number} generated.')
    return redirect('invoice_detail', pk=inv.pk)


@login_required
def invoice_from_so(request, so_id):
    """Generate invoice from a Sales Order."""
    from sales.models import SalesOrder
    so = get_object_or_404(SalesOrder, pk=so_id)

    existing = Invoice.objects.filter(sales_order=so).first()
    if existing:
        return redirect('invoice_detail', pk=existing.pk)

    inv = Invoice.objects.create(
        invoice_number=_next_invoice_number(),
        date=timezone.now().date(),
        sales_order=so,
        customer_name=so.customer.name if so.customer else '',
        customer_address=so.customer.address if so.customer else '',
        subtotal=sum(l.line_total for l in so.lines.all()),
        grand_total=sum(l.line_total for l in so.lines.all()),
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
    messages.success(request, f'Invoice {inv.invoice_number} generated.')
    return redirect('invoice_detail', pk=inv.pk)


@login_required
def invoice_detail(request, pk):
    inv = get_object_or_404(Invoice.objects.prefetch_related('lines', 'payments'), pk=pk)
    profile = BusinessProfile.get_instance()
    total_paid = sum(p.amount for p in inv.payments.all())
    balance_due = inv.grand_total - total_paid
    return render(request, 'core/invoice_detail.html', {
        'invoice': inv, 'profile': profile,
        'total_paid': total_paid, 'balance_due': balance_due,
    })


@login_required
def invoice_print(request, pk):
    inv = get_object_or_404(Invoice.objects.prefetch_related('lines'), pk=pk)
    profile = BusinessProfile.get_instance()
    return render(request, 'core/invoice_print.html', {'invoice': inv, 'profile': profile})


@login_required
def invoice_add_payment(request, pk):
    """Add a payment to an invoice. If fully paid, mark invoice as paid and auto-post linked SO."""
    inv = get_object_or_404(Invoice, pk=pk)
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

        InvoicePayment.objects.create(
            invoice=inv,
            date=timezone.now().date(),
            method=method,
            amount=amount,
            reference_no=reference_no,
            notes=notes,
            created_by=request.user,
        )
        messages.success(request, f'Payment of {amount} recorded.')

        # Check if fully paid
        total_paid = sum(p.amount for p in inv.payments.all())
        if total_paid >= inv.grand_total and not inv.is_paid:
            inv.is_paid = True
            inv.paid_at = timezone.now()
            inv.save(update_fields=['is_paid', 'paid_at', 'updated_at'])
            messages.success(request, f'Invoice {inv.invoice_number} marked as PAID.')

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

    return redirect('invoice_detail', pk=pk)


@login_required
def invoice_mark_paid(request, pk):
    """Manually mark an invoice as paid."""
    inv = get_object_or_404(Invoice, pk=pk)
    if request.method == 'POST':
        if not inv.is_paid:
            inv.is_paid = True
            inv.paid_at = timezone.now()
            inv.save(update_fields=['is_paid', 'paid_at', 'updated_at'])
            messages.success(request, f'Invoice {inv.invoice_number} marked as PAID.')

            # Auto-post linked SO
            if inv.sales_order:
                so = inv.sales_order
                from core.models import DocumentStatus
                if so.status == DocumentStatus.APPROVED:
                    so.status = DocumentStatus.POSTED
                    so.posted_by = request.user
                    so.posted_at = timezone.now()
                    so.save(update_fields=['status', 'posted_by', 'posted_at', 'updated_at'])
                    messages.info(request, f'Sales Order {so.document_number} auto-posted (invoice paid).')
        else:
            messages.info(request, 'Invoice is already paid.')
    return redirect('invoice_detail', pk=pk)


# ═══════════════════════════════════════════════════════════════════════════
# SUPPLIES INVENTORY
# ═══════════════════════════════════════════════════════════════════════════
@login_required
def supply_item_list(request):
    items = SupplyItem.objects.select_related('category')
    return render(request, 'core/supply_item_list.html', {'items': items})


@login_required
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
