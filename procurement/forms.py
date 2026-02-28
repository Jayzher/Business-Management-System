from django import forms
from django.forms import inlineformset_factory
from procurement.models import (
    PurchaseOrder, PurchaseOrderLine, GoodsReceipt, GoodsReceiptLine,
    PurchaseReturn, PurchaseReturnLine,
)


class PurchaseOrderForm(forms.ModelForm):
    class Meta:
        model = PurchaseOrder
        fields = ['document_number', 'supplier', 'warehouse', 'order_date', 'expected_date', 'notes']
        widgets = {
            'document_number': forms.TextInput(attrs={'class': 'form-control'}),
            'supplier': forms.Select(attrs={'class': 'form-control'}),
            'warehouse': forms.Select(attrs={'class': 'form-control'}),
            'order_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'expected_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
        help_texts = {
            'document_number': 'Unique PO number (e.g. PO-000001). Auto-generated if left blank.',
            'supplier': 'Vendor you are ordering from.',
            'warehouse': 'Destination warehouse for received goods.',
            'order_date': 'Date the order was placed.',
            'expected_date': 'Expected delivery date from supplier.',
            'notes': 'Internal remarks (payment terms, special instructions).',
        }


class PurchaseOrderLineForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound and (not getattr(self, 'instance', None) or not getattr(self.instance, 'pk', None)):
            for name in ['qty_ordered', 'unit_price']:
                if name in self.fields:
                    self.fields[name].initial = None

    class Meta:
        model = PurchaseOrderLine
        fields = ['item', 'qty_ordered', 'unit', 'unit_price', 'notes']
        widgets = {
            'item': forms.Select(attrs={'class': 'form-control form-control-sm'}),
            'qty_ordered': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.0001', 'placeholder': 'e.g., 10'}),
            'unit': forms.Select(attrs={'class': 'form-control form-control-sm'}),
            'unit_price': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.0001', 'placeholder': 'e.g., 150.00'}),
            'notes': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
        }
        help_texts = {
            'item': 'Product or material to order.',
            'qty_ordered': 'Quantity to purchase.',
            'unit': 'Unit of measure for this line.',
            'unit_price': 'Purchase cost per unit. Updates item cost price on GRN posting.',
            'notes': 'Optional line-level remarks.',
        }


PurchaseOrderLineFormSet = inlineformset_factory(
    PurchaseOrder, PurchaseOrderLine,
    form=PurchaseOrderLineForm,
    extra=1, can_delete=True,
)


class GoodsReceiptForm(forms.ModelForm):
    class Meta:
        model = GoodsReceipt
        fields = ['document_number', 'purchase_order', 'supplier', 'warehouse', 'receipt_date', 'notes']
        widgets = {
            'document_number': forms.TextInput(attrs={'class': 'form-control'}),
            'purchase_order': forms.Select(attrs={'class': 'form-control'}),
            'supplier': forms.Select(attrs={'class': 'form-control'}),
            'warehouse': forms.Select(attrs={'class': 'form-control'}),
            'receipt_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
        help_texts = {
            'document_number': 'Unique GRN number. Auto-generated if left blank.',
            'purchase_order': 'Link to a PO. Leave blank for direct receipts without a PO.',
            'supplier': 'Vendor delivering the goods.',
            'warehouse': 'Warehouse where goods are being received.',
            'receipt_date': 'Actual date goods were received.',
            'notes': 'Remarks about this receipt (condition, discrepancies).',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['purchase_order'].required = False


class GoodsReceiptLineForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound and (not getattr(self, 'instance', None) or not getattr(self.instance, 'pk', None)):
            if 'qty' in self.fields:
                self.fields['qty'].initial = None

    class Meta:
        model = GoodsReceiptLine
        fields = ['item', 'location', 'qty', 'unit', 'batch_number', 'serial_number', 'notes']
        widgets = {
            'item': forms.Select(attrs={'class': 'form-control form-control-sm'}),
            'location': forms.Select(attrs={'class': 'form-control form-control-sm'}),
            'qty': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.0001', 'placeholder': 'e.g., 5'}),
            'unit': forms.Select(attrs={'class': 'form-control form-control-sm'}),
            'batch_number': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
            'serial_number': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
            'notes': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
        }
        help_texts = {
            'item': 'Item being received.',
            'location': 'Exact bin/shelf location to put the stock into.',
            'qty': 'Quantity received for this line.',
            'unit': 'Unit of measure.',
            'batch_number': 'Batch/lot number for traceability.',
            'serial_number': 'Serial number for individually tracked items.',
            'notes': 'Line-level remarks.',
        }


GoodsReceiptLineFormSet = inlineformset_factory(
    GoodsReceipt, GoodsReceiptLine,
    form=GoodsReceiptLineForm,
    extra=1, can_delete=True,
)


class PurchaseReturnForm(forms.ModelForm):
    class Meta:
        model = PurchaseReturn
        fields = ['document_number', 'goods_receipt', 'supplier', 'warehouse', 'return_date', 'reason', 'notes']
        widgets = {
            'document_number': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
            'goods_receipt': forms.Select(attrs={'class': 'form-control form-control-sm'}),
            'supplier': forms.Select(attrs={'class': 'form-control form-control-sm'}),
            'warehouse': forms.Select(attrs={'class': 'form-control form-control-sm'}),
            'return_date': forms.DateInput(attrs={'class': 'form-control form-control-sm', 'type': 'date'}),
            'reason': forms.Textarea(attrs={'class': 'form-control form-control-sm', 'rows': 2}),
            'notes': forms.Textarea(attrs={'class': 'form-control form-control-sm', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['goods_receipt'].required = False


class PurchaseReturnLineForm(forms.ModelForm):
    class Meta:
        model = PurchaseReturnLine
        fields = ['item', 'location', 'qty', 'unit', 'reason', 'notes']
        widgets = {
            'item': forms.Select(attrs={'class': 'form-control form-control-sm'}),
            'location': forms.Select(attrs={'class': 'form-control form-control-sm'}),
            'qty': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.0001'}),
            'unit': forms.Select(attrs={'class': 'form-control form-control-sm'}),
            'reason': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
            'notes': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
        }


PurchaseReturnLineFormSet = inlineformset_factory(
    PurchaseReturn, PurchaseReturnLine,
    form=PurchaseReturnLineForm,
    extra=1, can_delete=True,
)
