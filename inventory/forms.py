from django import forms
from django.forms import inlineformset_factory
from decimal import Decimal
from inventory.models import (
    StockTransfer, StockTransferLine,
    StockAdjustment, StockAdjustmentLine,
    StockBalance,
    DamagedReport, DamagedReportLine,
    InventoryToSupplyTransfer, InventoryToSupplyTransferLine,
)


class StockTransferForm(forms.ModelForm):
    class Meta:
        model = StockTransfer
        fields = ['from_warehouse', 'to_warehouse', 'notes']
        widgets = {
            'from_warehouse': forms.Select(attrs={'class': 'form-control'}),
            'to_warehouse': forms.Select(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
        help_texts = {
            'from_warehouse': 'Source warehouse shipping the stock out.',
            'to_warehouse': 'Destination warehouse receiving the stock. Can be the same warehouse for bin-to-bin moves.',
            'notes': 'Reason for transfer or special instructions.',
        }


class StockTransferLineForm(forms.ModelForm):
    class Meta:
        model = StockTransferLine
        fields = ['item', 'from_location', 'to_location', 'qty', 'unit', 'batch_number', 'serial_number', 'notes']
        widgets = {
            'item': forms.Select(attrs={'class': 'form-control form-control-sm'}),
            'from_location': forms.Select(attrs={'class': 'form-control form-control-sm'}),
            'to_location': forms.Select(attrs={'class': 'form-control form-control-sm'}),
            'qty': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '1', 'min': '0', 'placeholder': 'e.g., 10'}),
            'unit': forms.Select(attrs={'class': 'form-control form-control-sm'}),
            'batch_number': forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Batch # (optional)'}),
            'serial_number': forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Serial # (optional)'}),
            'notes': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
        }


StockTransferLineFormSet = inlineformset_factory(
    StockTransfer, StockTransferLine,
    form=StockTransferLineForm,
    extra=1, can_delete=True,
)


class StockAdjustmentForm(forms.ModelForm):
    class Meta:
        model = StockAdjustment
        fields = ['warehouse', 'reason', 'notes']
        widgets = {
            'warehouse': forms.Select(attrs={'class': 'form-control'}),
            'reason': forms.TextInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
        help_texts = {
            'warehouse': 'Warehouse where the physical count was performed.',
            'reason': 'Brief reason for the adjustment (e.g. Cycle Count, Audit).',
            'notes': 'Additional details or approver remarks.',
        }


class StockAdjustmentLineForm(forms.ModelForm):
    """
    Physical-count line with two ways to specify the correction:
      - 'count'    : enter the counted total directly (qty_counted as-is).
      - 'increase' / 'decrease': enter a +/- delta; qty_counted is derived as
        qty_system ± delta, using the SAME system-qty read that gets stored
        on the line (see save()) — so the two numbers are never based on
        different snapshots of the balance.

    Either way, the stored fields are still just qty_counted/qty_system —
    this is a data-entry convenience, not a new persisted concept. The
    balance write itself (post_adjustment in services.py) is unchanged: it
    always SETs qty_on_hand to the resulting qty_counted, which is what
    makes a physical-count correction immune to whatever drift preceded it.
    A pure +/- delta replayed on top of a possibly-wrong running balance
    would NOT have that property, which is why the delta is resolved to an
    absolute qty_counted here rather than stored as a delta.
    """
    ADJUSTMENT_MODE_CHOICES = [
        ('count', 'Enter Counted Qty'),
        ('increase', 'Increase By'),
        ('decrease', 'Decrease By'),
    ]

    adjustment_mode = forms.ChoiceField(
        choices=ADJUSTMENT_MODE_CHOICES, required=False, initial='count',
        label='Adjustment Type',
        widget=forms.Select(attrs={'class': 'form-control form-control-sm adj-mode-select'}),
    )
    adjustment_delta = forms.DecimalField(
        required=False, min_value=Decimal('0'), label='Increase/Decrease By',
        widget=forms.NumberInput(attrs={
            'class': 'form-control form-control-sm adj-delta-input',
            'step': '1', 'min': '0', 'placeholder': 'Qty to add/remove',
        }),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        qty_system_widget = self.fields['qty_system'].widget
        qty_system_widget.attrs.update({
            'readonly': 'readonly',
            'data-system-qty': '1',
            'tabindex': '-1',
            'class': 'form-control form-control-sm bg-light',
        })
        # qty_counted is derived automatically in increase/decrease mode —
        # only required when the user enters a physical count directly.
        self.fields['qty_counted'].required = False

    @staticmethod
    def _system_qty(item, location):
        if not item or not location:
            return Decimal('0')

        qty_on_hand = (
            StockBalance.objects
            .filter(item=item, location=location)
            .values_list('qty_on_hand', flat=True)
            .first()
        )
        return qty_on_hand if qty_on_hand is not None else Decimal('0')

    def clean(self):
        cleaned_data = super().clean()
        item = cleaned_data.get('item')
        location = cleaned_data.get('location')

        if item and location:
            cleaned_data['qty_system'] = self._system_qty(item, location)

        mode = cleaned_data.get('adjustment_mode') or 'count'
        if mode in ('increase', 'decrease'):
            if cleaned_data.get('adjustment_delta') is None:
                self.add_error('adjustment_delta', 'Enter the quantity to increase/decrease by.')
            # qty_counted is resolved in save(), from the freshest system-qty
            # read at that moment — not here — so it and qty_system always
            # come from the same snapshot (see class docstring).
        elif cleaned_data.get('qty_counted') is None:
            self.add_error('qty_counted', 'Enter the counted quantity.')

        return cleaned_data

    def save(self, commit=True):
        item = self.cleaned_data.get('item') if hasattr(self, 'cleaned_data') else None
        location = self.cleaned_data.get('location') if hasattr(self, 'cleaned_data') else None
        system_qty = self._system_qty(item, location)
        self.instance.qty_system = system_qty

        mode = self.cleaned_data.get('adjustment_mode') or 'count'
        delta = self.cleaned_data.get('adjustment_delta')
        if mode == 'increase' and delta is not None:
            self.instance.qty_counted = system_qty + delta
        elif mode == 'decrease' and delta is not None:
            self.instance.qty_counted = system_qty - delta
        # mode == 'count': qty_counted keeps the value submitted directly.

        return super().save(commit=commit)

    class Meta:
        model = StockAdjustmentLine
        fields = ['item', 'location', 'qty_counted', 'qty_system', 'unit', 'batch_number', 'notes']
        labels = {
            'qty_counted': 'Counted Qty',
        }
        widgets = {
            'item': forms.Select(attrs={'class': 'form-control form-control-sm'}),
            'location': forms.Select(attrs={'class': 'form-control form-control-sm'}),
            'qty_counted': forms.NumberInput(attrs={'class': 'form-control form-control-sm qty-counted-input', 'step': '1', 'min': '0', 'placeholder': 'e.g., 50'}),
            'qty_system': forms.NumberInput(attrs={'class': 'form-control form-control-sm bg-light', 'step': '1', 'min': '0', 'placeholder': 'Auto-calculated', 'readonly': 'readonly', 'data-system-qty': '1', 'tabindex': '-1'}),
            'unit': forms.Select(attrs={'class': 'form-control form-control-sm'}),
            'batch_number': forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Batch # (optional)'}),
            'notes': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
        }


StockAdjustmentLineFormSet = inlineformset_factory(
    StockAdjustment, StockAdjustmentLine,
    form=StockAdjustmentLineForm,
    extra=1, can_delete=True,
)


class DamagedReportForm(forms.ModelForm):
    class Meta:
        model = DamagedReport
        fields = ['warehouse', 'notes']
        widgets = {
            'warehouse': forms.Select(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
        help_texts = {
            'warehouse': 'Warehouse where damage was discovered.',
            'notes': 'Summary of damage incident.',
        }


class DamagedReportLineForm(forms.ModelForm):
    class Meta:
        model = DamagedReportLine
        fields = ['item', 'location', 'qty', 'unit', 'batch_number', 'reason', 'photo', 'notes']
        widgets = {
            'item': forms.Select(attrs={'class': 'form-control form-control-sm'}),
            'location': forms.Select(attrs={'class': 'form-control form-control-sm'}),
            'qty': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '1', 'min': '0', 'placeholder': 'e.g., 2'}),
            'unit': forms.Select(attrs={'class': 'form-control form-control-sm'}),
            'batch_number': forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Batch # (optional)'}),
            'reason': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
            'photo': forms.ClearableFileInput(attrs={'class': 'form-control form-control-sm'}),
            'notes': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
        }


DamagedReportLineFormSet = inlineformset_factory(
    DamagedReport, DamagedReportLine,
    form=DamagedReportLineForm,
    extra=1, can_delete=True,
)


class InventoryToSupplyTransferForm(forms.ModelForm):
    class Meta:
        model = InventoryToSupplyTransfer
        fields = ['warehouse', 'transfer_date', 'reason', 'notes']
        widgets = {
            'warehouse': forms.Select(attrs={'class': 'form-control'}),
            'transfer_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'reason': forms.TextInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
        help_texts = {
            'warehouse': 'Warehouse where inventory stock is being taken from.',
            'transfer_date': 'Date of the transfer.',
            'reason': 'Brief reason for moving items to supply (e.g. Production use).',
            'notes': 'Additional remarks.',
        }


class InventoryToSupplyTransferLineForm(forms.ModelForm):
    class Meta:
        model = InventoryToSupplyTransferLine
        fields = ['item', 'location', 'supply_item', 'qty', 'unit', 'batch_number', 'notes']
        widgets = {
            'item': forms.Select(attrs={'class': 'form-control select2'}),
            'location': forms.Select(attrs={'class': 'form-control select2'}),
            'supply_item': forms.Select(attrs={'class': 'form-control select2'}),
            'qty': forms.NumberInput(attrs={'class': 'form-control', 'step': '1', 'min': '0'}),
            'unit': forms.Select(attrs={'class': 'form-control select2'}),
            'batch_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Optional'}),
            'notes': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Optional'}),
        }
        help_texts = {
            'item': 'Catalog item to transfer out of inventory',
            'location': 'Source location to deduct stock from',
            'supply_item': 'Optional: Leave blank to auto-create/find supply item based on catalog item',
            'qty': 'Quantity to transfer',
            'batch_number': 'Batch/lot number for traceability',
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['supply_item'].required = False


InventoryToSupplyTransferLineFormSet = inlineformset_factory(
    InventoryToSupplyTransfer, InventoryToSupplyTransferLine,
    form=InventoryToSupplyTransferLineForm,
    extra=1, can_delete=True,
)
