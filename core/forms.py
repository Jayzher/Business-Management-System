from django import forms
from core.models import (
    BusinessProfile, SalesChannel, ExpenseCategory, Expense,
    Invoice, SupplyCategory, SupplyItem, SupplyMovement, TargetGoal,
)


class BusinessProfileForm(forms.ModelForm):
    class Meta:
        model = BusinessProfile
        fields = [
            'name', 'tagline', 'owner_name', 'email', 'phone',
            'address', 'city', 'province', 'zip_code', 'country',
            'tin', 'logo', 'currency', 'fiscal_year_start_month',
            'receipt_footer',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'tagline': forms.TextInput(attrs={'class': 'form-control'}),
            'owner_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'city': forms.TextInput(attrs={'class': 'form-control'}),
            'province': forms.TextInput(attrs={'class': 'form-control'}),
            'zip_code': forms.TextInput(attrs={'class': 'form-control'}),
            'country': forms.TextInput(attrs={'class': 'form-control'}),
            'tin': forms.TextInput(attrs={'class': 'form-control'}),
            'logo': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'currency': forms.TextInput(attrs={'class': 'form-control'}),
            'fiscal_year_start_month': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 12}),
            'receipt_footer': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }


class SalesChannelForm(forms.ModelForm):
    class Meta:
        model = SalesChannel
        fields = ['name', 'code', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'code': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }


class ExpenseCategoryForm(forms.ModelForm):
    class Meta:
        model = ExpenseCategory
        fields = ['name', 'code', 'description', 'is_cogs']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'code': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'is_cogs': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class ExpenseForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound and (not getattr(self, 'instance', None) or not getattr(self.instance, 'pk', None)):
            if 'amount' in self.fields:
                self.fields['amount'].initial = None

    class Meta:
        model = Expense
        fields = [
            'date', 'category', 'item_description', 'amount', 'status',
            'vendor', 'business_address', 'reference_no', 'receipt_photo', 'memo',
        ]
        widgets = {
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'category': forms.Select(attrs={'class': 'form-control'}),
            'item_description': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Item or service description'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': 'e.g., 1250.00'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
            'vendor': forms.TextInput(attrs={'class': 'form-control'}),
            'business_address': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Vendor business address'}),
            'reference_no': forms.TextInput(attrs={'class': 'form-control'}),
            'receipt_photo': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'memo': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }


class SupplyCategoryForm(forms.ModelForm):
    class Meta:
        model = SupplyCategory
        fields = ['name', 'code']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'code': forms.TextInput(attrs={'class': 'form-control'}),
        }


class SupplyItemForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound and (not getattr(self, 'instance', None) or not getattr(self.instance, 'pk', None)):
            for name in ['cost_per_unit', 'minimum_stock']:
                if name in self.fields:
                    self.fields[name].initial = None

    class Meta:
        model = SupplyItem
        fields = [
            'name', 'code', 'category', 'supplier_brand', 'units_per_piece',
            'unit', 'cost_per_unit', 'minimum_stock', 'low_stock_alert_level', 'notes',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'code': forms.TextInput(attrs={'class': 'form-control'}),
            'category': forms.Select(attrs={'class': 'form-control'}),
            'supplier_brand': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Supplier or brand name'}),
            'units_per_piece': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.0001', 'placeholder': 'e.g., 1'}),
            'unit': forms.TextInput(attrs={'class': 'form-control'}),
            'cost_per_unit': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': 'e.g., 50.00'}),
            'minimum_stock': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.0001', 'placeholder': 'e.g., 5'}),
            'low_stock_alert_level': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.0001', 'placeholder': 'e.g., 10'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }


class SupplyMovementForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound and (not getattr(self, 'instance', None) or not getattr(self.instance, 'pk', None)):
            for name in ['qty', 'unit_cost']:
                if name in self.fields:
                    self.fields[name].initial = None

    class Meta:
        model = SupplyMovement
        fields = ['supply_item', 'movement_type', 'qty', 'unit_cost', 'date', 'notes']
        widgets = {
            'supply_item': forms.Select(attrs={'class': 'form-control'}),
            'movement_type': forms.Select(attrs={'class': 'form-control'}),
            'qty': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.0001', 'placeholder': 'e.g., 10'}),
            'unit_cost': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': 'e.g., 75.00'}),
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }


class TargetGoalForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound and (not getattr(self, 'instance', None) or not getattr(self.instance, 'pk', None)):
            for name in ['target_value', 'current_value']:
                if name in self.fields:
                    self.fields[name].initial = None

    class Meta:
        model = TargetGoal
        fields = [
            'title', 'description', 'category', 'target_value',
            'current_value', 'unit_label', 'priority', 'status',
            'due_date', 'assigned_to',
        ]
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'category': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Sales, Expenses'}),
            'target_value': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': 'e.g., 100000'}),
            'current_value': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': 'e.g., 25000'}),
            'unit_label': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. PHP, units'}),
            'priority': forms.Select(attrs={'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
            'due_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'assigned_to': forms.Select(attrs={'class': 'form-control'}),
        }
