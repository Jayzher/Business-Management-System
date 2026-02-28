from django import forms
from django.forms import inlineformset_factory
from sales.models import (
    SalesOrder, SalesOrderLine, DeliveryNote, DeliveryLine,
    SalesReturn, SalesReturnLine,
)


class SalesOrderForm(forms.ModelForm):
    class Meta:
        model = SalesOrder
        fields = ['document_number', 'customer', 'warehouse', 'order_date', 'delivery_date',
                  'fulfillment_type', 'shipping_address', 'currency', 'exchange_rate',
                  'payment_status', 'sales_channel', 'receipt_no', 'notes']
        widgets = {
            'document_number': forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'e.g., SO-000123'}),
            'customer': forms.Select(attrs={'class': 'form-control form-control-sm', 'data-placeholder': 'Select customer'}),
            'warehouse': forms.Select(attrs={'class': 'form-control form-control-sm', 'data-placeholder': 'Select warehouse'}),
            'order_date': forms.DateInput(attrs={'class': 'form-control form-control-sm', 'type': 'date'}),
            'delivery_date': forms.DateInput(attrs={'class': 'form-control form-control-sm', 'type': 'date'}),
            'fulfillment_type': forms.Select(attrs={'class': 'form-control form-control-sm'}),
            'shipping_address': forms.Textarea(attrs={'class': 'form-control form-control-sm', 'rows': 3, 'placeholder': 'Delivery address'}),
            'currency': forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'PHP'}),
            'exchange_rate': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.000001'}),
            'payment_status': forms.Select(attrs={'class': 'form-control form-control-sm'}),
            'sales_channel': forms.Select(attrs={'class': 'form-control form-control-sm'}),
            'receipt_no': forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Receipt / reference number'}),
            'notes': forms.Textarea(attrs={'class': 'form-control form-control-sm', 'rows': 3, 'placeholder': 'Internal notes or instructions'}),
        }
        help_texts = {
            'document_number': 'Unique SO number (e.g. SO-000001).',
            'customer': 'Customer placing this order.',
            'warehouse': 'Warehouse that will fulfill the order.',
            'order_date': 'Date the customer placed the order.',
            'delivery_date': 'Promised delivery date.',
            'fulfillment_type': 'Pickup: customer picks up. Delivery: items are shipped.',
            'shipping_address': 'Delivery address if different from customer address.',
            'currency': 'Transaction currency (default PHP).',
            'exchange_rate': 'Exchange rate to base currency (default 1).',
            'payment_status': 'Payment status of this order.',
            'sales_channel': 'Sales channel (e.g. Physical Store, Shopee).',
            'receipt_no': 'External receipt or reference number.',
            'notes': 'Internal remarks or special instructions.',
        }


class SalesOrderLineForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound and (not getattr(self, 'instance', None) or not getattr(self.instance, 'pk', None)):
            for name in ['qty_ordered', 'unit_price']:
                if name in self.fields:
                    self.fields[name].initial = None

    class Meta:
        model = SalesOrderLine
        fields = ['item', 'qty_ordered', 'unit', 'unit_price', 'discount_pct', 'notes']
        widgets = {
            'item': forms.Select(attrs={'class': 'form-control form-control-sm'}),
            'qty_ordered': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.0001', 'placeholder': 'e.g., 5'}),
            'unit': forms.Select(attrs={'class': 'form-control form-control-sm'}),
            'unit_price': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.0001', 'placeholder': 'e.g., 250.00'}),
            'discount_pct': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.01', 'placeholder': '0.00'}),
            'notes': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
        }
        help_texts = {
            'item': 'Product being sold.',
            'qty_ordered': 'Quantity the customer wants.',
            'unit': 'Unit of measure.',
            'unit_price': 'Selling price per unit. Used to compute line total and profit margin.',
            'discount_pct': 'Discount percentage for this line (e.g. 10 for 10%).',
            'notes': 'Optional line-level remarks.',
        }


SalesOrderLineFormSet = inlineformset_factory(
    SalesOrder, SalesOrderLine,
    form=SalesOrderLineForm,
    extra=1, can_delete=True,
)


class DeliveryNoteForm(forms.ModelForm):
    class Meta:
        model = DeliveryNote
        fields = ['document_number', 'sales_order', 'customer', 'warehouse', 'delivery_date',
                  'shipping_address', 'driver_name', 'vehicle_number', 'notes']
        widgets = {
            'document_number': forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'e.g., DN-000123'}),
            'sales_order': forms.Select(attrs={'class': 'form-control form-control-sm', 'data-placeholder': 'Optional: link to SO'}),
            'customer': forms.Select(attrs={'class': 'form-control form-control-sm', 'data-placeholder': 'Select customer'}),
            'warehouse': forms.Select(attrs={'class': 'form-control form-control-sm', 'data-placeholder': 'Select warehouse'}),
            'delivery_date': forms.DateInput(attrs={'class': 'form-control form-control-sm', 'type': 'date'}),
            'shipping_address': forms.Textarea(attrs={'class': 'form-control form-control-sm', 'rows': 3, 'placeholder': 'Ship-to address'}),
            'driver_name': forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Driver or courier name'}),
            'vehicle_number': forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Plate / tracking number'}),
            'notes': forms.Textarea(attrs={'class': 'form-control form-control-sm', 'rows': 3, 'placeholder': 'Special handling instructions'}),
        }
        help_texts = {
            'document_number': 'Unique delivery note number.',
            'sales_order': 'Link to an SO. Leave blank for direct deliveries.',
            'customer': 'Customer receiving the delivery.',
            'warehouse': 'Warehouse shipping the goods. Stock is deducted on posting.',
            'delivery_date': 'Actual shipment date.',
            'shipping_address': 'Override delivery address if needed.',
            'driver_name': 'Name of the driver/courier.',
            'vehicle_number': 'Vehicle or tracking number.',
            'notes': 'Delivery remarks or special handling instructions.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['sales_order'].required = False


class DeliveryLineForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound and (not getattr(self, 'instance', None) or not getattr(self.instance, 'pk', None)):
            if 'qty' in self.fields:
                self.fields['qty'].initial = None

    class Meta:
        model = DeliveryLine
        fields = ['item', 'location', 'qty', 'unit', 'notes']
        widgets = {
            'item': forms.Select(attrs={'class': 'form-control form-control-sm'}),
            'location': forms.Select(attrs={'class': 'form-control form-control-sm'}),
            'qty': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.0001', 'placeholder': 'e.g., 3'}),
            'unit': forms.Select(attrs={'class': 'form-control form-control-sm'}),
            'notes': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
        }
        help_texts = {
            'item': 'Item being shipped.',
            'location': 'Warehouse location to pick stock from.',
            'qty': 'Quantity to deliver.',
            'unit': 'Unit of measure.',
            'notes': 'Line-level delivery notes.',
        }


DeliveryLineFormSet = inlineformset_factory(
    DeliveryNote, DeliveryLine,
    form=DeliveryLineForm,
    extra=1, can_delete=True,
)


class SalesReturnForm(forms.ModelForm):
    class Meta:
        model = SalesReturn
        fields = ['document_number', 'sales_order', 'delivery_note', 'customer', 'warehouse', 'return_date', 'reason', 'notes']
        widgets = {
            'document_number': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
            'sales_order': forms.Select(attrs={'class': 'form-control form-control-sm'}),
            'delivery_note': forms.Select(attrs={'class': 'form-control form-control-sm'}),
            'customer': forms.Select(attrs={'class': 'form-control form-control-sm'}),
            'warehouse': forms.Select(attrs={'class': 'form-control form-control-sm'}),
            'return_date': forms.DateInput(attrs={'class': 'form-control form-control-sm', 'type': 'date'}),
            'reason': forms.Textarea(attrs={'class': 'form-control form-control-sm', 'rows': 2}),
            'notes': forms.Textarea(attrs={'class': 'form-control form-control-sm', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['sales_order'].required = False
        self.fields['delivery_note'].required = False


class SalesReturnLineForm(forms.ModelForm):
    class Meta:
        model = SalesReturnLine
        fields = ['item', 'location', 'qty', 'unit', 'reason', 'notes']
        widgets = {
            'item': forms.Select(attrs={'class': 'form-control form-control-sm'}),
            'location': forms.Select(attrs={'class': 'form-control form-control-sm'}),
            'qty': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.0001'}),
            'unit': forms.Select(attrs={'class': 'form-control form-control-sm'}),
            'reason': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
            'notes': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
        }


SalesReturnLineFormSet = inlineformset_factory(
    SalesReturn, SalesReturnLine,
    form=SalesReturnLineForm,
    extra=1, can_delete=True,
)
