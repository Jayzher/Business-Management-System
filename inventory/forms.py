from django import forms
from django.forms import inlineformset_factory
from inventory.models import (
    StockTransfer, StockTransferLine,
    StockAdjustment, StockAdjustmentLine,
    DamagedReport, DamagedReportLine,
)


class StockTransferForm(forms.ModelForm):
    class Meta:
        model = StockTransfer
        fields = ['document_number', 'from_warehouse', 'to_warehouse', 'notes']
        widgets = {
            'document_number': forms.TextInput(attrs={'class': 'form-control'}),
            'from_warehouse': forms.Select(attrs={'class': 'form-control'}),
            'to_warehouse': forms.Select(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
        help_texts = {
            'document_number': 'Unique transfer document number.',
            'from_warehouse': 'Source warehouse shipping the stock out.',
            'to_warehouse': 'Destination warehouse receiving the stock. Can be the same warehouse for bin-to-bin moves.',
            'notes': 'Reason for transfer or special instructions.',
        }


class StockTransferLineForm(forms.ModelForm):
    class Meta:
        model = StockTransferLine
        fields = ['item', 'from_location', 'to_location', 'qty', 'unit', 'notes']
        widgets = {
            'item': forms.Select(attrs={'class': 'form-control form-control-sm'}),
            'from_location': forms.Select(attrs={'class': 'form-control form-control-sm'}),
            'to_location': forms.Select(attrs={'class': 'form-control form-control-sm'}),
            'qty': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.0001', 'placeholder': 'e.g., 10'}),
            'unit': forms.Select(attrs={'class': 'form-control form-control-sm'}),
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
        fields = ['document_number', 'warehouse', 'reason', 'notes']
        widgets = {
            'document_number': forms.TextInput(attrs={'class': 'form-control'}),
            'warehouse': forms.Select(attrs={'class': 'form-control'}),
            'reason': forms.TextInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
        help_texts = {
            'document_number': 'Unique adjustment document number.',
            'warehouse': 'Warehouse where the physical count was performed.',
            'reason': 'Brief reason for the adjustment (e.g. Cycle Count, Audit).',
            'notes': 'Additional details or approver remarks.',
        }


class StockAdjustmentLineForm(forms.ModelForm):
    class Meta:
        model = StockAdjustmentLine
        fields = ['item', 'location', 'qty_counted', 'qty_system', 'unit', 'notes']
        widgets = {
            'item': forms.Select(attrs={'class': 'form-control form-control-sm'}),
            'location': forms.Select(attrs={'class': 'form-control form-control-sm'}),
            'qty_counted': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.0001', 'placeholder': 'e.g., 50'}),
            'qty_system': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.0001', 'placeholder': 'e.g., 48'}),
            'unit': forms.Select(attrs={'class': 'form-control form-control-sm'}),
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
        fields = ['document_number', 'warehouse', 'notes']
        widgets = {
            'document_number': forms.TextInput(attrs={'class': 'form-control'}),
            'warehouse': forms.Select(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
        help_texts = {
            'document_number': 'Unique damaged report number.',
            'warehouse': 'Warehouse where damage was discovered.',
            'notes': 'Summary of damage incident.',
        }


class DamagedReportLineForm(forms.ModelForm):
    class Meta:
        model = DamagedReportLine
        fields = ['item', 'location', 'qty', 'unit', 'reason', 'photo', 'notes']
        widgets = {
            'item': forms.Select(attrs={'class': 'form-control form-control-sm'}),
            'location': forms.Select(attrs={'class': 'form-control form-control-sm'}),
            'qty': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.0001', 'placeholder': 'e.g., 2'}),
            'unit': forms.Select(attrs={'class': 'form-control form-control-sm'}),
            'reason': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
            'photo': forms.ClearableFileInput(attrs={'class': 'form-control form-control-sm'}),
            'notes': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
        }


DamagedReportLineFormSet = inlineformset_factory(
    DamagedReport, DamagedReportLine,
    form=DamagedReportLineForm,
    extra=1, can_delete=True,
)
