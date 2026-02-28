from django import forms
from django.forms import inlineformset_factory
from pricing.models import PriceList, PriceListItem, DiscountRule


class PriceListForm(forms.ModelForm):
    class Meta:
        model = PriceList
        fields = ['name', 'warehouse', 'currency', 'is_default']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'warehouse': forms.Select(attrs={'class': 'form-control'}),
            'currency': forms.TextInput(attrs={'class': 'form-control'}),
            'is_default': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        help_texts = {
            'name': 'Descriptive name (e.g. Retail Prices, Wholesale Prices).',
            'warehouse': 'Limit this price list to a specific warehouse. Leave blank for global.',
            'currency': 'Currency code (e.g. PHP, USD).',
            'is_default': 'If checked, this price list is used as fallback when no register-specific list is assigned.',
        }


class PriceListItemForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound and (not getattr(self, 'instance', None) or not getattr(self.instance, 'pk', None)):
            for name in ['price', 'min_qty']:
                if name in self.fields:
                    self.fields[name].initial = None

    class Meta:
        model = PriceListItem
        fields = ['item', 'unit', 'price', 'min_qty', 'start_date', 'end_date']
        widgets = {
            'item': forms.Select(attrs={'class': 'form-control form-control-sm'}),
            'unit': forms.Select(attrs={'class': 'form-control form-control-sm'}),
            'price': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.01', 'placeholder': 'e.g., 199.99'}),
            'min_qty': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.0001', 'placeholder': 'e.g., 1'}),
            'start_date': forms.DateInput(attrs={'class': 'form-control form-control-sm', 'type': 'date'}),
            'end_date': forms.DateInput(attrs={'class': 'form-control form-control-sm', 'type': 'date'}),
        }


PriceListItemFormSet = inlineformset_factory(
    PriceList, PriceListItem,
    form=PriceListItemForm,
    extra=1, can_delete=True,
)


class DiscountRuleForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound and (not getattr(self, 'instance', None) or not getattr(self.instance, 'pk', None)):
            if 'value' in self.fields:
                self.fields['value'].initial = None

    class Meta:
        model = DiscountRule
        fields = ['name', 'discount_type', 'value', 'scope']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'discount_type': forms.Select(attrs={'class': 'form-control'}),
            'value': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': 'e.g., 10'}),
            'scope': forms.Select(attrs={'class': 'form-control'}),
        }
        help_texts = {
            'name': 'Descriptive rule name (e.g. Senior Citizen 20%, Bulk Order Flat 50).',
            'discount_type': 'Percentage = % off. Fixed Amount = flat currency deduction.',
            'value': 'Discount value. For percentage enter 20 for 20%. For fixed enter the amount.',
            'scope': 'Per Item = applied to each line. Per Order = applied once to the order total.',
        }
