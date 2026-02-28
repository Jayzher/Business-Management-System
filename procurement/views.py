from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from procurement.models import (
    PurchaseOrder, PurchaseOrderLine, GoodsReceipt, GoodsReceiptLine,
    PurchaseReturn, PurchaseReturnLine,
)
from procurement.serializers import PurchaseOrderSerializer, GoodsReceiptSerializer
from procurement.forms import (
    PurchaseOrderForm, PurchaseOrderLineFormSet,
    GoodsReceiptForm, GoodsReceiptLineFormSet,
    PurchaseReturnForm, PurchaseReturnLineFormSet,
)
from django.utils import timezone
from inventory.services import post_goods_receipt, cancel_document
from core.models import DocumentStatus
from accounts.decorators import procurement_access


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
            return Response({'status': 'posted', 'document_number': grn.document_number})
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


# ── Template Views ─────────────────────────────────────────────────────────

@login_required
@procurement_access
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
def goods_receipt_post_view(request, pk):
    grn = get_object_or_404(GoodsReceipt, pk=pk)
    if request.method == 'POST':
        try:
            post_goods_receipt(grn, request.user)
            messages.success(request, f'Goods Receipt {grn.document_number} posted. Stock updated.')
        except ValueError as e:
            messages.error(request, str(e))
    return redirect('goods_receipt_detail', pk=pk)


@login_required
@procurement_access
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
    orders = PurchaseOrder.objects.select_related('supplier', 'warehouse', 'created_by').all()
    return render(request, 'procurement/purchase_order_list.html', {'orders': orders})


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
    receipts = GoodsReceipt.objects.select_related(
        'purchase_order', 'supplier', 'warehouse', 'created_by'
    ).all()
    return render(request, 'procurement/goods_receipt_list.html', {'receipts': receipts})


@login_required
@procurement_access
def goods_receipt_detail_view(request, pk):
    receipt = get_object_or_404(
        GoodsReceipt.objects.select_related('purchase_order', 'supplier', 'warehouse', 'created_by', 'posted_by')
        .prefetch_related('lines__item', 'lines__unit', 'lines__location'), pk=pk
    )
    return render(request, 'procurement/goods_receipt_detail.html', {'receipt': receipt})


@login_required
@procurement_access
def purchase_order_create_view(request):
    if request.method == 'POST':
        form = PurchaseOrderForm(request.POST)
        formset = PurchaseOrderLineFormSet(request.POST)
        if form.is_valid():
            po = form.save(commit=False)
            po.created_by = request.user
            po.save()
            formset = PurchaseOrderLineFormSet(request.POST, instance=po)
            if formset.is_valid():
                formset.save()
                messages.success(request, f'Purchase Order {po.document_number} created.')
                return redirect('purchase_order_detail', pk=po.pk)
    else:
        form = PurchaseOrderForm()
        formset = PurchaseOrderLineFormSet()
    return render(request, 'procurement/purchase_order_form.html', {
        'form': form, 'formset': formset, 'title': 'Create Purchase Order',
    })


@login_required
@procurement_access
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
def purchase_order_delete_view(request, pk):
    po = get_object_or_404(PurchaseOrder, pk=pk)
    if request.method == 'POST':
        po.soft_delete()
        messages.success(request, f'Purchase Order {po.document_number} deleted.')
        return redirect('purchase_order_list')
    return render(request, 'procurement/purchase_order_delete.html', {'object': po})


@login_required
@procurement_access
def goods_receipt_create_view(request):
    if request.method == 'POST':
        form = GoodsReceiptForm(request.POST)
        formset = GoodsReceiptLineFormSet(request.POST, request.FILES)
        if form.is_valid():
            grn = form.save(commit=False)
            grn.created_by = request.user
            grn.save()
            formset = GoodsReceiptLineFormSet(request.POST, request.FILES, instance=grn)
            if formset.is_valid():
                formset.save()
                messages.success(request, f'Goods Receipt {grn.document_number} created.')
                return redirect('goods_receipt_detail', pk=grn.pk)
    else:
        form = GoodsReceiptForm()
        formset = GoodsReceiptLineFormSet()
    return render(request, 'procurement/goods_receipt_form.html', {
        'form': form, 'formset': formset, 'title': 'Create Goods Receipt',
    })


@login_required
@procurement_access
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
    returns = PurchaseReturn.objects.select_related('supplier', 'warehouse', 'created_by').all()
    return render(request, 'procurement/purchase_return_list.html', {'returns': returns})


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
def purchase_return_create_view(request):
    if request.method == 'POST':
        form = PurchaseReturnForm(request.POST)
        formset = PurchaseReturnLineFormSet(request.POST)
        if form.is_valid():
            pr = form.save(commit=False)
            pr.created_by = request.user
            pr.save()
            formset = PurchaseReturnLineFormSet(request.POST, instance=pr)
            if formset.is_valid():
                formset.save()
                messages.success(request, f'Purchase Return {pr.document_number} created.')
                return redirect('purchase_return_detail', pk=pr.pk)
    else:
        form = PurchaseReturnForm()
        formset = PurchaseReturnLineFormSet()
    return render(request, 'procurement/purchase_return_form.html', {
        'form': form, 'formset': formset, 'title': 'Create Purchase Return',
    })


@login_required
@procurement_access
def purchase_return_post_view(request, pk):
    pr = get_object_or_404(PurchaseReturn, pk=pk)
    if request.method == 'POST':
        try:
            from inventory.services import post_purchase_return
            post_purchase_return(pr, request.user)
            messages.success(request, f'Purchase Return {pr.document_number} posted. Stock updated.')
        except ValueError as e:
            messages.error(request, str(e))
    return redirect('purchase_return_detail', pk=pk)


@login_required
@procurement_access
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
def purchase_return_delete_view(request, pk):
    pr = get_object_or_404(PurchaseReturn, pk=pk)
    if request.method == 'POST':
        pr.soft_delete()
        messages.success(request, f'Purchase Return {pr.document_number} deleted.')
        return redirect('purchase_return_list')
    return render(request, 'core/confirm_delete.html', {'object': pr, 'cancel_url': 'purchase_return_list'})
