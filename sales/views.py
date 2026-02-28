from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from sales.models import SalesOrder, DeliveryNote, SalesReturn, SalesReturnLine
from sales.serializers import SalesOrderSerializer, DeliveryNoteSerializer
from sales.forms import (
    SalesOrderForm, SalesOrderLineFormSet,
    DeliveryNoteForm, DeliveryLineFormSet,
    SalesReturnForm, SalesReturnLineFormSet,
)
from django.utils import timezone
from inventory.services import post_delivery, reserve_stock, cancel_document
from core.models import DocumentStatus
from accounts.decorators import sales_access


# ── API Views ──────────────────────────────────────────────────────────────

class SalesOrderViewSet(viewsets.ModelViewSet):
    queryset = SalesOrder.objects.select_related(
        'customer', 'warehouse', 'created_by'
    ).prefetch_related('lines').all()
    serializer_class = SalesOrderSerializer
    filterset_fields = ['status', 'customer', 'warehouse']
    search_fields = ['document_number', 'customer__name']

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        so = self.get_object()
        if so.status != DocumentStatus.DRAFT:
            return Response({'error': 'Only DRAFT sales orders can be approved.'}, status=status.HTTP_400_BAD_REQUEST)
        from django.utils import timezone
        so.status = DocumentStatus.APPROVED
        so.approved_by = request.user
        so.approved_at = timezone.now()
        so.save(update_fields=['status', 'approved_by', 'approved_at', 'updated_at'])
        # Auto-create Delivery Note + Invoice
        from inventory.automation import auto_create_delivery_from_so, auto_create_invoice_from_so
        result = {'status': 'approved'}
        dn = auto_create_delivery_from_so(so, request.user)
        if dn:
            result['delivery_document_number'] = dn.document_number
        inv = auto_create_invoice_from_so(so, request.user)
        if inv:
            result['invoice_number'] = inv.invoice_number
        return Response(result)

    @action(detail=True, methods=['post'])
    def reserve(self, request, pk=None):
        so = self.get_object()
        if so.status != DocumentStatus.APPROVED:
            return Response(
                {'error': 'Only APPROVED sales orders can be reserved.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        errors = []
        for line in so.lines.select_related('item', 'unit').all():
            if line.qty_reserved >= line.qty_ordered:
                continue
            qty_to_reserve = line.qty_ordered - line.qty_reserved
            from inventory.models import StockBalance
            balances = StockBalance.objects.filter(
                item=line.item,
                location__warehouse=so.warehouse,
            ).order_by('-qty_on_hand')
            remaining = qty_to_reserve
            for bal in balances:
                available = bal.qty_on_hand - bal.qty_reserved
                if available <= 0:
                    continue
                reserve_qty = min(remaining, available)
                try:
                    reserve_stock(
                        line.item, bal.location, reserve_qty,
                        'SalesOrder', so.pk, request.user,
                    )
                    remaining -= reserve_qty
                    line.qty_reserved += reserve_qty
                except ValueError:
                    continue
                if remaining <= 0:
                    break
            line.save(update_fields=['qty_reserved'])
            if remaining > 0:
                errors.append(f"{line.item.code}: could not reserve {remaining}")
        if errors:
            return Response({'status': 'partial', 'errors': errors})
        return Response({'status': 'reserved'})


class DeliveryNoteViewSet(viewsets.ModelViewSet):
    queryset = DeliveryNote.objects.select_related(
        'sales_order', 'customer', 'warehouse', 'created_by'
    ).prefetch_related('lines').all()
    serializer_class = DeliveryNoteSerializer
    filterset_fields = ['status', 'customer', 'warehouse']
    search_fields = ['document_number', 'customer__name']

    @action(detail=True, methods=['post'], url_path='post')
    def post_delivery(self, request, pk=None):
        delivery = self.get_object()
        try:
            post_delivery(delivery, request.user)
            return Response({'status': 'posted', 'document_number': delivery.document_number})
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


# ── Template Views ─────────────────────────────────────────────────────────

@login_required
@sales_access
def sales_order_approve_view(request, pk):
    so = get_object_or_404(SalesOrder, pk=pk)
    if request.method == 'POST':
        if so.status != DocumentStatus.DRAFT:
            messages.error(request, 'Only DRAFT sales orders can be approved.')
        else:
            so.status = DocumentStatus.APPROVED
            so.approved_by = request.user
            so.approved_at = timezone.now()
            so.save(update_fields=['status', 'approved_by', 'approved_at', 'updated_at'])
            messages.success(request, f'Sales Order {so.document_number} approved.')
            # Auto-create Delivery Note
            from inventory.automation import auto_create_delivery_from_so, auto_create_invoice_from_so
            dn = auto_create_delivery_from_so(so, request.user)
            if dn:
                messages.info(request, f'Delivery Note {dn.document_number} auto-created.')
            # Auto-create Invoice
            inv = auto_create_invoice_from_so(so, request.user)
            if inv:
                messages.info(request, f'Invoice {inv.invoice_number} auto-created.')
    return redirect('sales_order_detail', pk=pk)


@login_required
@sales_access
def sales_order_cancel_view(request, pk):
    so = get_object_or_404(SalesOrder, pk=pk)
    if request.method == 'POST':
        try:
            cancel_document(so, request.user)
            messages.success(request, f'Sales Order {so.document_number} cancelled.')
        except ValueError as e:
            messages.error(request, str(e))
    return redirect('sales_order_detail', pk=pk)


@login_required
@sales_access
def delivery_post_view(request, pk):
    dn = get_object_or_404(DeliveryNote, pk=pk)
    if request.method == 'POST':
        try:
            post_delivery(dn, request.user)
            messages.success(request, f'Delivery Note {dn.document_number} posted. Stock updated.')
            # Auto-create Invoice from delivery
            from inventory.automation import auto_create_invoice_from_delivery
            inv = auto_create_invoice_from_delivery(dn, request.user)
            if inv:
                messages.info(request, f'Invoice {inv.invoice_number} auto-created.')
        except ValueError as e:
            messages.error(request, str(e))
    return redirect('delivery_detail', pk=pk)


@login_required
@sales_access
def delivery_cancel_view(request, pk):
    dn = get_object_or_404(DeliveryNote, pk=pk)
    if request.method == 'POST':
        try:
            cancel_document(dn, request.user)
            messages.success(request, f'Delivery Note {dn.document_number} cancelled.')
        except ValueError as e:
            messages.error(request, str(e))
    return redirect('delivery_detail', pk=pk)


@login_required
@sales_access
def sales_order_print_view(request, pk):
    from core.models import BusinessProfile
    order = get_object_or_404(
        SalesOrder.objects.select_related('customer', 'warehouse', 'created_by', 'approved_by')
        .prefetch_related('lines__item', 'lines__unit'), pk=pk
    )
    profile = BusinessProfile.get_instance()
    return render(request, 'sales/sales_order_print.html', {
        'doc': order, 'doc_title': 'SALES ORDER', 'doc_number': order.document_number, 'profile': profile,
    })


@login_required
@sales_access
def delivery_print_view(request, pk):
    from core.models import BusinessProfile
    dn = get_object_or_404(
        DeliveryNote.objects.select_related('sales_order', 'customer', 'warehouse', 'created_by', 'approved_by')
        .prefetch_related('lines__item', 'lines__unit', 'lines__location'), pk=pk
    )
    profile = BusinessProfile.get_instance()
    return render(request, 'sales/delivery_note_print.html', {
        'doc': dn, 'doc_title': 'DELIVERY NOTE', 'doc_number': dn.document_number, 'profile': profile,
    })


@login_required
@sales_access
def sales_order_list_view(request):
    orders = SalesOrder.objects.select_related('customer', 'warehouse', 'created_by').all()
    return render(request, 'sales/sales_order_list.html', {'orders': orders})


@login_required
@sales_access
def sales_order_detail_view(request, pk):
    order = get_object_or_404(
        SalesOrder.objects.select_related('customer', 'warehouse', 'created_by', 'approved_by', 'posted_by')
        .prefetch_related('lines__item', 'lines__unit'), pk=pk
    )
    return render(request, 'sales/sales_order_detail.html', {'order': order})


@login_required
@sales_access
def delivery_list_view(request):
    deliveries = DeliveryNote.objects.select_related(
        'sales_order', 'customer', 'warehouse', 'created_by'
    ).all()
    return render(request, 'sales/delivery_list.html', {'deliveries': deliveries})


@login_required
@sales_access
def delivery_detail_view(request, pk):
    delivery = get_object_or_404(
        DeliveryNote.objects.select_related('sales_order', 'customer', 'warehouse', 'created_by', 'posted_by')
        .prefetch_related('lines__item', 'lines__unit', 'lines__location'), pk=pk
    )
    return render(request, 'sales/delivery_detail.html', {'delivery': delivery})


@login_required
@sales_access
def sales_order_create_view(request):
    if request.method == 'POST':
        form = SalesOrderForm(request.POST)
        formset = SalesOrderLineFormSet(request.POST)
        if form.is_valid():
            so = form.save(commit=False)
            so.created_by = request.user
            so.save()
            formset = SalesOrderLineFormSet(request.POST, instance=so)
            if formset.is_valid():
                formset.save()
                messages.success(request, f'Sales Order {so.document_number} created.')
                return redirect('sales_order_detail', pk=so.pk)
    else:
        form = SalesOrderForm()
        formset = SalesOrderLineFormSet()
    return render(request, 'sales/sales_order_form.html', {
        'form': form, 'formset': formset, 'title': 'Create Sales Order',
    })


@login_required
@sales_access
def sales_order_edit_view(request, pk):
    so = get_object_or_404(SalesOrder, pk=pk)
    if so.status != 'DRAFT':
        messages.error(request, 'Only DRAFT sales orders can be edited.')
        return redirect('sales_order_detail', pk=pk)
    if request.method == 'POST':
        form = SalesOrderForm(request.POST, instance=so)
        formset = SalesOrderLineFormSet(request.POST, instance=so)
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            messages.success(request, f'Sales Order {so.document_number} updated.')
            return redirect('sales_order_detail', pk=so.pk)
    else:
        form = SalesOrderForm(instance=so)
        formset = SalesOrderLineFormSet(instance=so)
    return render(request, 'sales/sales_order_form.html', {
        'form': form, 'formset': formset, 'title': f'Edit SO: {so.document_number}',
    })


@login_required
@sales_access
def sales_order_delete_view(request, pk):
    so = get_object_or_404(SalesOrder, pk=pk)
    if request.method == 'POST':
        so.soft_delete()
        messages.success(request, f'Sales Order {so.document_number} deleted.')
        return redirect('sales_order_list')
    return render(request, 'sales/sales_order_delete.html', {'object': so})


@login_required
@sales_access
def delivery_create_view(request):
    if request.method == 'POST':
        form = DeliveryNoteForm(request.POST)
        formset = DeliveryLineFormSet(request.POST)
        if form.is_valid():
            dn = form.save(commit=False)
            dn.created_by = request.user
            dn.save()
            formset = DeliveryLineFormSet(request.POST, instance=dn)
            if formset.is_valid():
                formset.save()
                messages.success(request, f'Delivery Note {dn.document_number} created.')
                return redirect('delivery_detail', pk=dn.pk)
    else:
        form = DeliveryNoteForm()
        formset = DeliveryLineFormSet()
    return render(request, 'sales/delivery_form.html', {
        'form': form, 'formset': formset, 'title': 'Create Delivery Note',
    })


@login_required
@sales_access
def delivery_edit_view(request, pk):
    dn = get_object_or_404(DeliveryNote, pk=pk)
    if dn.status != 'DRAFT':
        messages.error(request, 'Only DRAFT deliveries can be edited.')
        return redirect('delivery_detail', pk=pk)
    if request.method == 'POST':
        form = DeliveryNoteForm(request.POST, instance=dn)
        formset = DeliveryLineFormSet(request.POST, instance=dn)
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            messages.success(request, f'Delivery Note {dn.document_number} updated.')
            return redirect('delivery_detail', pk=dn.pk)
    else:
        form = DeliveryNoteForm(instance=dn)
        formset = DeliveryLineFormSet(instance=dn)
    return render(request, 'sales/delivery_form.html', {
        'form': form, 'formset': formset, 'title': f'Edit DN: {dn.document_number}',
    })


@login_required
@sales_access
def delivery_delete_view(request, pk):
    dn = get_object_or_404(DeliveryNote, pk=pk)
    if request.method == 'POST':
        dn.soft_delete()
        messages.success(request, f'Delivery Note {dn.document_number} deleted.')
        return redirect('delivery_list')
    return render(request, 'sales/delivery_delete.html', {'object': dn})


# ── Sales Returns ─────────────────────────────────────────────────────────

@login_required
@sales_access
def sales_return_list_view(request):
    returns = SalesReturn.objects.select_related('customer', 'warehouse', 'created_by').all()
    return render(request, 'sales/sales_return_list.html', {'returns': returns})


@login_required
@sales_access
def sales_return_detail_view(request, pk):
    sr = get_object_or_404(
        SalesReturn.objects.select_related('sales_order', 'delivery_note', 'customer', 'warehouse', 'created_by', 'posted_by')
        .prefetch_related('lines__item', 'lines__unit', 'lines__location'), pk=pk
    )
    return render(request, 'sales/sales_return_detail.html', {'sr': sr})


@login_required
@sales_access
def sales_return_create_view(request):
    if request.method == 'POST':
        form = SalesReturnForm(request.POST)
        formset = SalesReturnLineFormSet(request.POST)
        if form.is_valid():
            sr = form.save(commit=False)
            sr.created_by = request.user
            sr.save()
            formset = SalesReturnLineFormSet(request.POST, instance=sr)
            if formset.is_valid():
                formset.save()
                messages.success(request, f'Sales Return {sr.document_number} created.')
                return redirect('sales_return_detail', pk=sr.pk)
    else:
        form = SalesReturnForm()
        formset = SalesReturnLineFormSet()
    return render(request, 'sales/sales_return_form.html', {
        'form': form, 'formset': formset, 'title': 'Create Sales Return',
    })


@login_required
@sales_access
def sales_return_post_view(request, pk):
    sr = get_object_or_404(SalesReturn, pk=pk)
    if request.method == 'POST':
        try:
            from inventory.services import post_sales_return
            post_sales_return(sr, request.user)
            messages.success(request, f'Sales Return {sr.document_number} posted. Stock updated.')
        except ValueError as e:
            messages.error(request, str(e))
    return redirect('sales_return_detail', pk=pk)


@login_required
@sales_access
def sales_return_cancel_view(request, pk):
    sr = get_object_or_404(SalesReturn, pk=pk)
    if request.method == 'POST':
        try:
            cancel_document(sr, request.user)
            messages.success(request, f'Sales Return {sr.document_number} cancelled.')
        except ValueError as e:
            messages.error(request, str(e))
    return redirect('sales_return_detail', pk=pk)


@login_required
@sales_access
def sales_return_delete_view(request, pk):
    sr = get_object_or_404(SalesReturn, pk=pk)
    if request.method == 'POST':
        sr.soft_delete()
        messages.success(request, f'Sales Return {sr.document_number} deleted.')
        return redirect('sales_return_list')
    return render(request, 'core/confirm_delete.html', {'object': sr, 'cancel_url': 'sales_return_list'})
