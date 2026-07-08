from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction as db_transaction
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from procurement.models import (
    PurchaseOrder, PurchaseOrderLine, GoodsReceipt, GoodsReceiptLine,
    PurchaseReturn, PurchaseReturnLine, GoodsReceiptAttachment,
    SupplierCatalogEntry,
)
from procurement.serializers import PurchaseOrderSerializer, GoodsReceiptSerializer
from procurement.forms import (
    PurchaseOrderForm, PurchaseOrderLineFormSet,
    GoodsReceiptForm, GoodsReceiptLineFormSet, GoodsReceiptAttachmentForm,
    PurchaseReturnForm, PurchaseReturnLineFormSet,
    SupplierCatalogEntryForm,
)
from django.utils import timezone
from inventory.services import post_goods_receipt, cancel_document
from inventory.services import save_with_document_number
from core.models import DocumentStatus
from accounts.decorators import write_denied_for_viewer,  procurement_access
from django.http import HttpResponseRedirect


# ── API Views ──────────────────────────────────────────────────────────────

class PurchaseOrderViewSet(viewsets.ModelViewSet):
    queryset = PurchaseOrder.objects.select_related(
        'supplier', 'warehouse', 'created_by'
    ).prefetch_related('lines').all()
    serializer_class = PurchaseOrderSerializer
    filterset_fields = ['status', 'supplier', 'warehouse']
    search_fields = ['document_number', 'supplier__name']

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        po = self.get_object()
        if po.status != DocumentStatus.DRAFT:
            return Response({'error': 'Only DRAFT POs can be approved.'}, status=status.HTTP_400_BAD_REQUEST)
        from django.utils import timezone
        po.status = DocumentStatus.APPROVED
        po.approved_by = request.user
        po.approved_at = timezone.now()
        po.save(update_fields=['status', 'approved_by', 'approved_at', 'updated_at'])
        # Auto-create GRN
        from inventory.automation import auto_create_grn_from_po
        grn = auto_create_grn_from_po(po, request.user)
        result = {'status': 'approved'}
        if grn:
            result['grn_document_number'] = grn.document_number
        return Response(result)


class GoodsReceiptViewSet(viewsets.ModelViewSet):
    queryset = GoodsReceipt.objects.select_related(
        'purchase_order', 'supplier', 'warehouse', 'created_by'
    ).prefetch_related('lines').all()
    serializer_class = GoodsReceiptSerializer
    filterset_fields = ['status', 'supplier', 'warehouse']
    search_fields = ['document_number', 'supplier__name']

    @action(detail=True, methods=['post'], url_path='post')
    def post_receipt(self, request, pk=None):
        grn = self.get_object()
        try:
            post_goods_receipt(grn, request.user)
            result = {'status': 'posted', 'document_number': grn.document_number}
            skipped = getattr(grn, 'skipped_lines', [])
            if skipped:
                result['skipped_lines'] = skipped
                result['warning'] = (
                    f'{len(skipped)} line(s) skipped due to incompatible units. '
                    f'Add the missing Unit Conversions under Catalog → Unit Conversions.'
                )
            return Response(result)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


# ── Template Views ─────────────────────────────────────────────────────────

@login_required
@procurement_access
@write_denied_for_viewer
def purchase_order_approve_view(request, pk):
    po = get_object_or_404(PurchaseOrder, pk=pk)
    if request.method == 'POST':
        if po.status != DocumentStatus.DRAFT:
            messages.error(request, 'Only DRAFT purchase orders can be approved.')
        else:
            po.status = DocumentStatus.APPROVED
            po.approved_by = request.user
            po.approved_at = timezone.now()
            po.save(update_fields=['status', 'approved_by', 'approved_at', 'updated_at'])
            messages.success(request, f'Purchase Order {po.document_number} approved.')
            # Auto-create Goods Receipt
            from inventory.automation import auto_create_grn_from_po
            grn = auto_create_grn_from_po(po, request.user)
            if grn:
                messages.info(request, f'Goods Receipt {grn.document_number} auto-created.')
    return redirect('purchase_order_detail', pk=pk)


@login_required
@procurement_access
@write_denied_for_viewer
def purchase_order_cancel_view(request, pk):
    po = get_object_or_404(PurchaseOrder, pk=pk)
    if request.method == 'POST':
        try:
            cancel_document(po, request.user)
            messages.success(request, f'Purchase Order {po.document_number} cancelled.')
        except ValueError as e:
            messages.error(request, str(e))
    return redirect('purchase_order_detail', pk=pk)


@login_required
@procurement_access
@write_denied_for_viewer
def goods_receipt_post_view(request, pk):
    grn = get_object_or_404(GoodsReceipt, pk=pk)
    if request.method == 'POST':
        try:
            post_goods_receipt(grn, request.user)
            from inventory.services import format_skipped_lines_message
            warning = format_skipped_lines_message(grn)
            if warning:
                messages.warning(request, warning)
            else:
                messages.success(request, f'Goods Receipt {grn.document_number} posted. Stock updated.')
        except ValueError as e:
            messages.error(request, str(e))
    return redirect('goods_receipt_detail', pk=pk)


@login_required
@procurement_access
@write_denied_for_viewer
def goods_receipt_cancel_view(request, pk):
    grn = get_object_or_404(GoodsReceipt, pk=pk)
    if request.method == 'POST':
        try:
            cancel_document(grn, request.user)
            messages.success(request, f'Goods Receipt {grn.document_number} cancelled.')
        except ValueError as e:
            messages.error(request, str(e))
    return redirect('goods_receipt_detail', pk=pk)


@login_required
@procurement_access
def purchase_order_print_view(request, pk):
    from core.models import BusinessProfile
    order = get_object_or_404(
        PurchaseOrder.objects.select_related('supplier', 'warehouse', 'created_by', 'approved_by')
        .prefetch_related('lines__item', 'lines__unit'), pk=pk
    )
    profile = BusinessProfile.get_instance()
    return render(request, 'procurement/purchase_order_print.html', {
        'doc': order, 'doc_title': 'PURCHASE ORDER', 'doc_number': order.document_number, 'profile': profile,
    })


@login_required
@procurement_access
def goods_receipt_print_view(request, pk):
    from core.models import BusinessProfile
    receipt = get_object_or_404(
        GoodsReceipt.objects.select_related('purchase_order', 'supplier', 'warehouse', 'created_by', 'approved_by')
        .prefetch_related('lines__item', 'lines__unit', 'lines__location'), pk=pk
    )
    profile = BusinessProfile.get_instance()
    return render(request, 'procurement/goods_receipt_print.html', {
        'doc': receipt, 'doc_title': 'GOODS RECEIPT', 'doc_number': receipt.document_number, 'profile': profile,
    })


@login_required
@procurement_access
def purchase_order_list_view(request):
    from core.utils import sort_queryset, paginate_queryset, search_queryset
    orders = PurchaseOrder.objects.select_related('supplier', 'warehouse', 'created_by').all()
    orders = search_queryset(request, orders, ['document_number', 'supplier__name'])
    status_filter = (request.GET.get('status') or '').strip()
    if status_filter:
        orders = orders.filter(status=status_filter)
    sort_map = {
        'number': 'document_number',
        'supplier': 'supplier__name',
        'warehouse': 'warehouse__code',
        'date': 'order_date',
        'status': 'status',
        'by': 'created_by__username',
    }
    orders, sort, direction = sort_queryset(request, orders, sort_map, default_key='created_at', default_dir='desc')
    page_obj = paginate_queryset(request, orders, per_page=25)
    filters = [{
        'param': 'status',
        'label': 'Status',
        'options': list(DocumentStatus.choices),
    }]
    return render(request, 'procurement/purchase_order_list.html', {
        'orders': page_obj,
        'page_obj': page_obj,
        'sort': sort,
        'dir': direction,
        'filters': filters,
    })


@login_required
@procurement_access
def purchase_order_detail_view(request, pk):
    order = get_object_or_404(
        PurchaseOrder.objects.select_related('supplier', 'warehouse', 'created_by', 'approved_by', 'posted_by')
        .prefetch_related('lines__item', 'lines__unit'), pk=pk
    )
    return render(request, 'procurement/purchase_order_detail.html', {'order': order})


@login_required
@procurement_access
def goods_receipt_list_view(request):
    from core.utils import sort_queryset, paginate_queryset, search_queryset
    receipts = GoodsReceipt.objects.select_related(
        'purchase_order', 'supplier', 'warehouse', 'created_by'
    ).all()
    receipts = search_queryset(request, receipts, [
        'document_number', 'purchase_order__document_number', 'supplier__name',
    ])
    status_filter = (request.GET.get('status') or '').strip()
    if status_filter:
        receipts = receipts.filter(status=status_filter)
    sort_map = {
        'number': 'document_number',
        'po': 'purchase_order__document_number',
        'supplier': 'supplier__name',
        'warehouse': 'warehouse__code',
        'date': 'receipt_date',
        'status': 'status',
        'by': 'created_by__username',
    }
    receipts, sort, direction = sort_queryset(request, receipts, sort_map, default_key='created_at', default_dir='desc')
    page_obj = paginate_queryset(request, receipts, per_page=25)
    filters = [{
        'param': 'status',
        'label': 'Status',
        'options': list(DocumentStatus.choices),
    }]
    return render(request, 'procurement/goods_receipt_list.html', {
        'receipts': page_obj,
        'page_obj': page_obj,
        'sort': sort,
        'dir': direction,
        'filters': filters,
    })


@login_required
@procurement_access
def goods_receipt_detail_view(request, pk):
    receipt = get_object_or_404(
        GoodsReceipt.objects.select_related('purchase_order', 'supplier', 'warehouse', 'created_by', 'posted_by')
        .prefetch_related('lines__item', 'lines__unit', 'lines__location', 'attachments'), pk=pk
    )
    attach_form = GoodsReceiptAttachmentForm()
    return render(request, 'procurement/goods_receipt_detail.html', {
        'receipt': receipt,
        'attach_form': attach_form,
    })


@login_required
@procurement_access
@write_denied_for_viewer
def goods_receipt_attachment_upload(request, pk):
    receipt = get_object_or_404(GoodsReceipt, pk=pk)
    if request.method == 'POST':
        form = GoodsReceiptAttachmentForm(request.POST, request.FILES)
        files = request.FILES.getlist('file')
        if files:
            for f in files:
                GoodsReceiptAttachment.objects.create(
                    goods_receipt=receipt,
                    file=f,
                    original_name=getattr(f, 'name', ''),
                    uploaded_by=request.user,
                )
        elif form.is_valid():
            # Fallback single file (unlikely because widget is multiple)
            f = form.cleaned_data['file']
            GoodsReceiptAttachment.objects.create(
                goods_receipt=receipt,
                file=f,
                original_name=getattr(f, 'name', ''),
                uploaded_by=request.user,
            )
    return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/procurement/goods-receipts/'))


@login_required
@procurement_access
@write_denied_for_viewer
def goods_receipt_attachment_delete(request, pk, attachment_id):
    receipt = get_object_or_404(GoodsReceipt, pk=pk)
    attachment = get_object_or_404(GoodsReceiptAttachment, pk=attachment_id, goods_receipt=receipt)
    if request.method == 'POST':
        attachment.delete()
    return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/procurement/goods-receipts/'))


@login_required
@procurement_access
@write_denied_for_viewer
def purchase_order_create_view(request):
    if request.method == 'POST':
        form = PurchaseOrderForm(request.POST)
        formset = PurchaseOrderLineFormSet(request.POST)
        form_valid = form.is_valid()
        formset_valid = formset.is_valid()
        if form_valid and formset_valid:
            po = form.save(commit=False)
            po.created_by = request.user
            save_with_document_number(po, 'PO', PurchaseOrder)
            formset.instance = po
            formset.save()
            messages.success(request, f'Purchase Order {po.document_number} created.')
            return redirect('purchase_order_detail', pk=po.pk)
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = PurchaseOrderForm()
        formset = PurchaseOrderLineFormSet()
    return render(request, 'procurement/purchase_order_form.html', {
        'form': form, 'formset': formset, 'title': 'Create Purchase Order',
    })


@login_required
@procurement_access
@write_denied_for_viewer
def purchase_order_edit_view(request, pk):
    po = get_object_or_404(PurchaseOrder, pk=pk)
    if po.status != 'DRAFT':
        messages.error(request, 'Only DRAFT purchase orders can be edited.')
        return redirect('purchase_order_detail', pk=pk)
    if request.method == 'POST':
        form = PurchaseOrderForm(request.POST, instance=po)
        formset = PurchaseOrderLineFormSet(request.POST, instance=po)
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            messages.success(request, f'Purchase Order {po.document_number} updated.')
            return redirect('purchase_order_detail', pk=po.pk)
    else:
        form = PurchaseOrderForm(instance=po)
        formset = PurchaseOrderLineFormSet(instance=po)
    return render(request, 'procurement/purchase_order_form.html', {
        'form': form, 'formset': formset, 'title': f'Edit PO: {po.document_number}',
    })


@login_required
@procurement_access
@write_denied_for_viewer
def purchase_order_delete_view(request, pk):
    po = get_object_or_404(PurchaseOrder, pk=pk)
    if request.method == 'POST':
        po.soft_delete()
        messages.success(request, f'Purchase Order {po.document_number} deleted.')
        return redirect('purchase_order_list')
    return render(request, 'procurement/purchase_order_delete.html', {'object': po})


@login_required
@procurement_access
@write_denied_for_viewer
def goods_receipt_create_view(request):
    if request.method == 'POST':
        form = GoodsReceiptForm(request.POST)
        formset = GoodsReceiptLineFormSet(request.POST, request.FILES)
        form_valid = form.is_valid()
        formset_valid = formset.is_valid()
        if form_valid and formset_valid:
            grn = form.save(commit=False)
            grn.created_by = request.user
            save_with_document_number(grn, 'GRN', GoodsReceipt)
            formset.instance = grn
            formset.save()
            messages.success(request, f'Goods Receipt {grn.document_number} created.')
            return redirect('goods_receipt_detail', pk=grn.pk)
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = GoodsReceiptForm()
        formset = GoodsReceiptLineFormSet()
    return render(request, 'procurement/goods_receipt_form.html', {
        'form': form, 'formset': formset, 'title': 'Create Goods Receipt',
    })


@login_required
@procurement_access
@write_denied_for_viewer
def goods_receipt_edit_view(request, pk):
    grn = get_object_or_404(GoodsReceipt, pk=pk)
    if grn.status != 'DRAFT':
        messages.error(request, 'Only DRAFT goods receipts can be edited.')
        return redirect('goods_receipt_detail', pk=pk)
    if request.method == 'POST':
        form = GoodsReceiptForm(request.POST, instance=grn)
        formset = GoodsReceiptLineFormSet(request.POST, request.FILES, instance=grn)
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            messages.success(request, f'Goods Receipt {grn.document_number} updated.')
            return redirect('goods_receipt_detail', pk=grn.pk)
    else:
        form = GoodsReceiptForm(instance=grn)
        formset = GoodsReceiptLineFormSet(instance=grn)
    return render(request, 'procurement/goods_receipt_form.html', {
        'form': form, 'formset': formset, 'title': f'Edit GRN: {grn.document_number}',
    })


@login_required
@procurement_access
@write_denied_for_viewer
def goods_receipt_delete_view(request, pk):
    grn = get_object_or_404(GoodsReceipt, pk=pk)
    if request.method == 'POST':
        grn.soft_delete()
        messages.success(request, f'Goods Receipt {grn.document_number} deleted.')
        return redirect('goods_receipt_list')
    return render(request, 'procurement/goods_receipt_delete.html', {'object': grn})


# ── Purchase Returns ──────────────────────────────────────────────────────

@login_required
@procurement_access
def purchase_return_list_view(request):
    from core.utils import sort_queryset, paginate_queryset, search_queryset
    returns = PurchaseReturn.objects.select_related('supplier', 'warehouse', 'created_by').all()
    returns = search_queryset(request, returns, ['document_number', 'supplier__name'])
    status_filter = (request.GET.get('status') or '').strip()
    if status_filter:
        returns = returns.filter(status=status_filter)
    sort_map = {
        'number': 'document_number',
        'supplier': 'supplier__name',
        'warehouse': 'warehouse__name',
        'date': 'return_date',
        'status': 'status',
        'by': 'created_by__username',
    }
    returns, sort, direction = sort_queryset(request, returns, sort_map, default_key='created_at', default_dir='desc')
    page_obj = paginate_queryset(request, returns, per_page=25)
    filters = [{
        'param': 'status',
        'label': 'Status',
        'options': list(DocumentStatus.choices),
    }]
    return render(request, 'procurement/purchase_return_list.html', {
        'returns': page_obj,
        'page_obj': page_obj,
        'sort': sort,
        'dir': direction,
        'filters': filters,
    })


@login_required
@procurement_access
def purchase_return_detail_view(request, pk):
    pr = get_object_or_404(
        PurchaseReturn.objects.select_related('goods_receipt', 'supplier', 'warehouse', 'created_by', 'posted_by')
        .prefetch_related('lines__item', 'lines__unit', 'lines__location'), pk=pk
    )
    return render(request, 'procurement/purchase_return_detail.html', {'pr': pr})


@login_required
@procurement_access
@write_denied_for_viewer
def purchase_return_create_view(request):
    if request.method == 'POST':
        form = PurchaseReturnForm(request.POST)
        formset = PurchaseReturnLineFormSet(request.POST)
        form_valid = form.is_valid()
        formset_valid = formset.is_valid()
        if form_valid and formset_valid:
            pr = form.save(commit=False)
            pr.created_by = request.user
            save_with_document_number(pr, 'PR', PurchaseReturn)
            formset.instance = pr
            formset.save()
            messages.success(request, f'Purchase Return {pr.document_number} created.')
            return redirect('purchase_return_detail', pk=pr.pk)
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = PurchaseReturnForm()
        formset = PurchaseReturnLineFormSet()
    return render(request, 'procurement/purchase_return_form.html', {
        'form': form, 'formset': formset, 'title': 'Create Purchase Return',
    })


@login_required
@procurement_access
@write_denied_for_viewer
def purchase_return_edit_view(request, pk):
    pr = get_object_or_404(PurchaseReturn, pk=pk)
    if pr.status != 'DRAFT':
        messages.error(request, 'Only DRAFT purchase returns can be edited.')
        return redirect('purchase_return_detail', pk=pk)
    if request.method == 'POST':
        form = PurchaseReturnForm(request.POST, instance=pr)
        formset = PurchaseReturnLineFormSet(request.POST, instance=pr)
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            messages.success(request, f'Purchase Return {pr.document_number} updated.')
            return redirect('purchase_return_detail', pk=pr.pk)
    else:
        form = PurchaseReturnForm(instance=pr)
        formset = PurchaseReturnLineFormSet(instance=pr)
    return render(request, 'procurement/purchase_return_form.html', {
        'form': form, 'formset': formset, 'title': f'Edit Return: {pr.document_number}',
    })


@login_required
@procurement_access
@write_denied_for_viewer
def purchase_return_post_view(request, pk):
    pr = get_object_or_404(PurchaseReturn, pk=pk)
    if request.method == 'POST':
        try:
            from inventory.services import post_purchase_return
            post_purchase_return(pr, request.user)
            from inventory.services import format_skipped_lines_message
            warning = format_skipped_lines_message(pr)
            if warning:
                messages.warning(request, warning)
            else:
                messages.success(request, f'Purchase Return {pr.document_number} posted. Stock updated.')
        except ValueError as e:
            messages.error(request, str(e))
    return redirect('purchase_return_detail', pk=pk)


@login_required
@procurement_access
@write_denied_for_viewer
def purchase_return_cancel_view(request, pk):
    pr = get_object_or_404(PurchaseReturn, pk=pk)
    if request.method == 'POST':
        try:
            cancel_document(pr, request.user)
            messages.success(request, f'Purchase Return {pr.document_number} cancelled.')
        except ValueError as e:
            messages.error(request, str(e))
    return redirect('purchase_return_detail', pk=pk)


@login_required
@procurement_access
@write_denied_for_viewer
def purchase_return_delete_view(request, pk):
    pr = get_object_or_404(PurchaseReturn, pk=pk)
    if request.method == 'POST':
        pr.soft_delete()
        messages.success(request, f'Purchase Return {pr.document_number} deleted.')
        return redirect('purchase_return_list')
    return render(request, 'core/confirm_delete.html', {'object': pr, 'cancel_url': 'purchase_return_list'})


# ── Supplier Catalog ───────────────────────────────────────────────────────


def _update_item_cost_from_supplier_catalog(item_ids=None):
    """
    Seed Item.cost_price from supplier catalog entries — but ONLY for items
    that have no *priced* posted GRN history yet.

    Rationale: the GRN posting flow (inventory.services.post_goods_receipt)
    maintains a weighted-average cost in stock_unit. That number is the
    authoritative cost for any item that has actually been received and
    priced. Letting a catalog-sync overwrite it would clobber real receipt
    history with a quote-list MAX. So once an item has a posted GRN that
    resulted in cost_price > 0, the catalog sync leaves it alone.

    However, "has a posted GRN" isn't the same as "has a priced GRN" — every
    line on that GRN may have been skipped by the WAC calc (a $0 PO price, or
    a cross-unit PO price with no UnitConversion available), leaving
    cost_price at its unpriced 0 default. In that case the item is still
    treated as unpriced, and the supplier-catalog MAX price is used to
    rescue it instead of leaving 0 in place forever.

    For items with NO posted GRN, we still use the MAX-across-suppliers price
    converted to default_unit, so cost-of-quotation reports have a sensible
    starting value before goods arrive.

    Prices in a non-base unit are converted with raise_on_missing=True so a
    bad/missing conversion is skipped (no silent fallback to the unconverted
    price).

    Returns:
        dict with keys:
            updated_count   – items whose cost_price changed
            unchanged_count – items whose price was already correct
            skipped_count   – items skipped (no priceable entries, or item has GRN history)
    """
    from decimal import Decimal
    from catalog.models import Item
    from catalog.utils import convert_price_for_unit
    from procurement.models import GoodsReceiptLine
    from core.models import DocumentStatus

    qs = SupplierCatalogEntry.objects.select_related('item', 'item__default_unit', 'unit')
    if item_ids is not None:
        qs = qs.filter(item_id__in=list(item_ids))

    # Bucket entries by item
    per_item = {}
    for entry in qs:
        per_item.setdefault(entry.item_id, (entry.item, []))[1].append(entry)

    # Items with at least one POSTED GRN line — their cost_price is governed
    # by post_goods_receipt's weighted-average and must NOT be overwritten.
    items_with_grn_history = set(
        GoodsReceiptLine.objects
        .filter(
            goods_receipt__status=DocumentStatus.POSTED,
            item_id__in=list(per_item.keys()),
        )
        .values_list('item_id', flat=True)
        .distinct()
    )

    updated_count = 0
    unchanged_count = 0
    skipped_count = 0
    _updated_pks = []

    for item_id, (item, entries) in per_item.items():
        # GRN history only wins if it actually produced a price. If every GRN
        # line for this item was skipped (e.g. a $0 PO line, or a cross-unit
        # PO price with no conversion available), cost_price is still sitting
        # at its unpriced default — in that case fall through and let the
        # supplier-catalog price rescue it instead of leaving it stuck at 0.
        if item_id in items_with_grn_history and (item.cost_price or Decimal('0')) > 0:
            skipped_count += 1
            continue

        base_unit = item.default_unit
        best_price = None
        for e in entries:
            if not e.unit_price or e.unit_price <= 0:
                continue
            if e.unit_id == base_unit.pk:
                price_in_base = Decimal(str(e.unit_price))
            else:
                try:
                    price_in_base = convert_price_for_unit(
                        e.unit_price, e.unit, base_unit,
                        item=item, use_conversion_price=False,
                        raise_on_missing=True,
                    )
                except ValueError:
                    # Missing conversion — silently skip this catalog entry
                    continue

            if best_price is None or price_in_base > best_price:
                best_price = price_in_base

        if best_price is None:
            skipped_count += 1
            continue

        current = item.cost_price or Decimal('0')
        best_price_q = best_price.quantize(Decimal('0.0001'))
        if current.quantize(Decimal('0.0001')) == best_price_q:
            unchanged_count += 1
            continue

        Item.objects.filter(pk=item.pk).update(cost_price=best_price_q)
        _updated_pks.append(item.pk)
        updated_count += 1

    if _updated_pks:
        from sync.signals import bulk_sync_upsert
        bulk_sync_upsert(Item, _updated_pks)

    return {
        'updated_count': updated_count,
        'unchanged_count': unchanged_count,
        'skipped_count': skipped_count,
    }


@login_required
@procurement_access
def supplier_catalog_list_view(request):
    """
    Matrix view: rows = items, columns = suppliers.
    Each cell shows that supplier's unit price for the item.
    The cheapest price per item is highlighted.
    """
    from catalog.models import Item
    from partners.models import Supplier
    from core.utils import search_queryset, paginate_queryset

    supplier_id = (request.GET.get('supplier') or '').strip()
    item_type = (request.GET.get('type') or '').strip()

    entries_qs = SupplierCatalogEntry.objects.select_related(
        'supplier', 'item', 'item__category', 'unit',
    ).all()

    if supplier_id:
        entries_qs = entries_qs.filter(supplier_id=supplier_id)
    if item_type:
        entries_qs = entries_qs.filter(item__item_type=item_type)
    entries_qs = search_queryset(request, entries_qs, ['item__code', 'item__name'])

    # Build the matrix data
    # Collect all suppliers and items that appear in entries, and the
    # cheapest price per item, in a single pass over the (cached) queryset.
    price_map = {}      # {(item_id, supplier_id): entry}
    item_ids = set()
    supplier_ids = set()
    cheapest_map = {}   # item_id -> min unit_price

    for entry in entries_qs:
        price_map[(entry.item_id, entry.supplier_id)] = entry
        item_ids.add(entry.item_id)
        supplier_ids.add(entry.supplier_id)
        if entry.item_id not in cheapest_map or entry.unit_price < cheapest_map[entry.item_id]:
            cheapest_map[entry.item_id] = entry.unit_price

    # Get ordered objects
    suppliers = Supplier.objects.filter(pk__in=supplier_ids).order_by('name')
    items_qs = Item.objects.filter(pk__in=item_ids).select_related('category', 'default_unit').order_by('code')
    page_obj = paginate_queryset(request, items_qs, per_page=25)

    # Build rows (current page of items only; columns stay the full
    # filtered supplier set so the matrix layout stays consistent)
    rows = []
    for item in page_obj:
        cells = []
        for sup in suppliers:
            entry = price_map.get((item.pk, sup.pk))
            is_cheapest = (
                entry is not None
                and cheapest_map.get(item.pk) is not None
                and entry.unit_price == cheapest_map[item.pk]
            )
            cells.append({
                'entry': entry,
                'is_cheapest': is_cheapest,
            })
        rows.append({
            'item': item,
            'cells': cells,
        })

    # For filter dropdowns
    all_suppliers = Supplier.objects.order_by('name')
    filters = [
        {
            'param': 'supplier',
            'label': 'Supplier',
            'options': [(s.pk, f'{s.code} - {s.name}') for s in all_suppliers],
        },
        {
            'param': 'type',
            'label': 'Item Type',
            'options': [('RAW', 'Raw Material'), ('FINISHED', 'Finished Product'), ('SERVICE', 'Service')],
        },
    ]

    return render(request, 'procurement/supplier_catalog_list.html', {
        'rows': rows,
        'page_obj': page_obj,
        'suppliers': suppliers,
        'filters': filters,
        'total_items': page_obj.paginator.count,
        'total_suppliers': suppliers.count(),
        'total_entries': len(price_map),
    })


@login_required
@procurement_access
def supplier_catalog_by_supplier_view(request):
    """
    Per-supplier view: lists all catalog entries for a selected supplier.
    """
    from partners.models import Supplier
    from core.utils import sort_queryset, paginate_queryset, search_queryset

    supplier_id = (request.GET.get('supplier') or '').strip()

    entries = SupplierCatalogEntry.objects.select_related(
        'supplier', 'item', 'item__category', 'unit',
    )

    if supplier_id:
        entries = entries.filter(supplier_id=supplier_id)
    entries = search_queryset(request, entries, ['item__code', 'item__name'])

    sort_map = {
        'supplier': 'supplier__name',
        'item': 'item__code',
        'name': 'item__name',
        'category': 'item__category__name',
        'price': 'unit_price',
        'unit': 'unit__abbreviation',
        'currency': 'currency',
        'lead_time': 'lead_time_days',
        'last_po': 'last_po_number',
        'last_po_date': 'last_po_date',
    }
    entries, sort, direction = sort_queryset(request, entries, sort_map, default_key='created_at', default_dir='desc')
    page_obj = paginate_queryset(request, entries, per_page=25)

    all_suppliers = Supplier.objects.order_by('name')
    filters = [{
        'param': 'supplier',
        'label': 'Supplier',
        'options': [(s.pk, f'{s.code} - {s.name}') for s in all_suppliers],
    }]

    return render(request, 'procurement/supplier_catalog_by_supplier.html', {
        'entries': page_obj,
        'page_obj': page_obj,
        'sort': sort,
        'dir': direction,
        'filters': filters,
    })


@login_required
@procurement_access
@write_denied_for_viewer
def supplier_catalog_create_view(request):
    if request.method == 'POST':
        form = SupplierCatalogEntryForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Supplier catalog entry created.')
            return redirect('supplier_catalog_list')
    else:
        form = SupplierCatalogEntryForm()
    return render(request, 'procurement/supplier_catalog_form.html', {
        'form': form, 'title': 'Add Supplier Catalog Entry',
    })


@login_required
@procurement_access
@write_denied_for_viewer
def supplier_catalog_edit_view(request, pk):
    entry = get_object_or_404(SupplierCatalogEntry, pk=pk)
    if request.method == 'POST':
        form = SupplierCatalogEntryForm(request.POST, instance=entry)
        if form.is_valid():
            form.save()
            messages.success(request, 'Supplier catalog entry updated.')
            return redirect('supplier_catalog_list')
    else:
        form = SupplierCatalogEntryForm(instance=entry)
    return render(request, 'procurement/supplier_catalog_form.html', {
        'form': form, 'title': 'Edit Supplier Catalog Entry',
    })


@login_required
@procurement_access
@write_denied_for_viewer
def supplier_catalog_delete_view(request, pk):
    entry = get_object_or_404(SupplierCatalogEntry, pk=pk)
    if request.method == 'POST':
        entry.delete()
        messages.success(request, 'Supplier catalog entry deleted.')
        return redirect('supplier_catalog_list')
    return render(request, 'core/confirm_delete.html', {
        'object': entry, 'cancel_url': 'supplier_catalog_list',
    })


@login_required
@procurement_access
@write_denied_for_viewer
def supplier_catalog_sync_view(request):
    """
    Sync supplier catalog from past PO data.
    For each POSTED or APPROVED PO line, upsert the latest unit_price into SupplierCatalogEntry.
    After syncing, each affected Item's cost_price is updated to the highest
    supplier price on record (converted to the item's default unit).
    """
    if request.method == 'POST':
        from decimal import Decimal

        # Get all PO lines from posted/approved POs
        po_lines = (
            PurchaseOrderLine.objects
            .filter(purchase_order__status__in=['POSTED', 'APPROVED'])
            .select_related('purchase_order__supplier', 'item', 'unit')
            .order_by('purchase_order__order_date')
        )

        created_count = 0
        updated_count = 0
        touched_items = set()

        for line in po_lines:
            if not line.unit_price or line.unit_price <= 0:
                continue

            po = line.purchase_order
            entry, created = SupplierCatalogEntry.objects.update_or_create(
                supplier=po.supplier,
                item=line.item,
                unit=line.unit,
                defaults={
                    'unit_price': line.unit_price,
                    'currency': po.currency or 'PHP',
                    'last_po_date': po.order_date,
                    'last_po_number': po.document_number,
                },
            )
            if created:
                created_count += 1
            else:
                updated_count += 1
            touched_items.add(line.item_id)

        # ── Update Item.cost_price to the highest supplier price ──
        cost_stats = _update_item_cost_from_supplier_catalog(
            item_ids=touched_items or None
        )

        messages.success(
            request,
            f'Sync complete: {created_count} new entries created, '
            f'{updated_count} entries updated from past PO data. '
            f'Item costs updated: {cost_stats["updated_count"]} '
            f'(unchanged: {cost_stats["unchanged_count"]}, '
            f'skipped: {cost_stats["skipped_count"]}).',
        )
        return redirect('supplier_catalog_list')

    # GET: show confirmation page
    po_count = (
        PurchaseOrder.objects
        .filter(status__in=['POSTED', 'APPROVED'])
        .count()
    )
    line_count = (
        PurchaseOrderLine.objects
        .filter(
            purchase_order__status__in=['POSTED', 'APPROVED'],
            unit_price__gt=0,
        )
        .count()
    )
    return render(request, 'procurement/supplier_catalog_sync.html', {
        'po_count': po_count,
        'line_count': line_count,
    })


@login_required
@procurement_access
@write_denied_for_viewer
def supplier_catalog_sync_grn_view(request):
    """
    Sync supplier catalog from GRN data (posted GRNs linked to POs).
    Always keeps the latest price based on receipt_date.
    After syncing, each affected Item's cost_price is updated to the highest
    supplier price on record (converted to the item's default unit).
    """
    if request.method == 'POST':
        # Get all posted GRN lines that have an associated PO
        grn_lines = (
            GoodsReceiptLine.objects
            .filter(
                goods_receipt__status='POSTED',
                goods_receipt__purchase_order__isnull=False,
            )
            .select_related(
                'goods_receipt__supplier',
                'goods_receipt__purchase_order',
                'item', 'unit',
            )
            .order_by('goods_receipt__receipt_date')
        )

        created_count = 0
        updated_count = 0
        fallback_unit_count = 0
        touched_items = set()

        for grn_line in grn_lines:
            grn = grn_line.goods_receipt
            # Match by item AND unit first; fall back to any other PO line for the item.
            po_line = (
                PurchaseOrderLine.objects
                .filter(
                    purchase_order=grn.purchase_order,
                    item=grn_line.item,
                    unit=grn_line.unit,
                )
                .first()
            )

            if po_line and po_line.unit_price and po_line.unit_price > 0:
                entry_unit = grn_line.unit
                entry_price = po_line.unit_price  # GRN unit == PO unit
            else:
                # No PO line in the GRN's receiving unit. Record the entry in
                # the PO's OWN unit with its own exact price rather than
                # converting into the GRN's unit here — that conversion would
                # be undone (and re-rounded) a moment later when
                # _update_item_cost_from_supplier_catalog() converts
                # entry.unit -> item.default_unit anyway. Chaining two
                # independently-rounded conversions can drift the final cost
                # by a centavo even when the underlying supplier price was a
                # clean whole number. Storing the PO's original unit+price
                # keeps this down to the one conversion that's unavoidable.
                fallback_po = (
                    PurchaseOrderLine.objects
                    .filter(purchase_order=grn.purchase_order, item=grn_line.item)
                    .exclude(unit_price__isnull=True)
                    .exclude(unit_price__lte=0)
                    .first()
                )
                if not fallback_po:
                    continue
                entry_unit = fallback_po.unit
                entry_price = fallback_po.unit_price
                fallback_unit_count += 1

            existing = SupplierCatalogEntry.objects.filter(
                supplier=grn.supplier,
                item=grn_line.item,
                unit=entry_unit,
            ).first()

            if existing and existing.last_po_date and existing.last_po_date >= grn.receipt_date:
                continue

            entry, created = SupplierCatalogEntry.objects.update_or_create(
                supplier=grn.supplier,
                item=grn_line.item,
                unit=entry_unit,
                defaults={
                    'unit_price': entry_price,
                    'currency': grn.purchase_order.currency or 'PHP',
                    'last_po_date': grn.receipt_date,
                    'last_po_number': grn.document_number,
                },
            )
            if created:
                created_count += 1
            else:
                updated_count += 1
            touched_items.add(grn_line.item_id)

        # ── Update Item.cost_price to the highest supplier price ──
        cost_stats = _update_item_cost_from_supplier_catalog(
            item_ids=touched_items or None
        )

        messages.success(
            request,
            f'GRN Sync complete: {created_count} new entries created, '
            f'{updated_count} entries updated from Goods Receipts '
            f'({fallback_unit_count} recorded in their original PO unit — '
            f'no matching PO line in the GRN\'s receiving unit). '
            f'Item costs updated: {cost_stats["updated_count"]} '
            f'(unchanged: {cost_stats["unchanged_count"]}, '
            f'skipped: {cost_stats["skipped_count"]}).',
        )
        return redirect('supplier_catalog_list')

    # GET: show confirmation page
    grn_count = (
        GoodsReceipt.objects
        .filter(status='POSTED', purchase_order__isnull=False)
        .count()
    )
    grn_line_count = (
        GoodsReceiptLine.objects
        .filter(
            goods_receipt__status='POSTED',
            goods_receipt__purchase_order__isnull=False,
        )
        .count()
    )
    return render(request, 'procurement/supplier_catalog_sync_grn.html', {
        'grn_count': grn_count,
        'grn_line_count': grn_line_count,
    })
