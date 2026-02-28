from django import forms
from pos.models import POSRegister, CashEntry


class POSRegisterForm(forms.ModelForm):
    class Meta:
        model = POSRegister
        fields = ['name', 'warehouse', 'default_location', 'price_list', 'receipt_footer']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'warehouse': forms.Select(attrs={'class': 'form-control'}),
            'default_location': forms.Select(attrs={'class': 'form-control'}),
            'price_list': forms.Select(attrs={'class': 'form-control'}),
            'receipt_footer': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
        help_texts = {
            'name': 'Display name for this register (e.g. Counter 1, Drive-Through).',
            'warehouse': 'Warehouse this register sells from. Stock is deducted here.',
            'default_location': 'Default bin/location for stock deductions in this register.',
            'price_list': 'Price list used for item pricing. Falls back to default price list if empty.',
            'receipt_footer': 'Custom text printed at the bottom of receipts (e.g. Thank you!).',
        }


class OpenShiftForm(forms.Form):
    register = forms.ModelChoiceField(
        queryset=POSRegister.objects.filter(is_active=True),
        widget=forms.Select(attrs={'class': 'form-control'}),
        help_text='Select the register to open a shift on. Only one shift can be open per register.',
    )
    opening_cash = forms.DecimalField(
        max_digits=15, decimal_places=2, required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': 'e.g., 1000.00'}),
        help_text='Cash amount in the drawer at shift start. Used to calculate expected cash at close.',
    )


class CloseShiftForm(forms.Form):
    closing_cash_declared = forms.DecimalField(
        max_digits=15, decimal_places=2,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': 'e.g., 1200.00'}),
        help_text='Count the physical cash in the drawer and enter the total. System compares this against expected cash to show variance.',
    )


class CashEntryForm(forms.ModelForm):
    class Meta:
        model = CashEntry
        fields = ['entry_type', 'amount', 'reason']
        widgets = {
            'entry_type': forms.Select(attrs={'class': 'form-control'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': 'e.g., 500.00'}),
            'reason': forms.TextInput(attrs={'class': 'form-control'}),
        }
        help_texts = {
            'entry_type': 'Cash In = money added to drawer. Cash Out = money removed.',
            'amount': 'Amount of cash being added or removed.',
            'reason': 'Reason for this cash movement (e.g. Change fund, Petty cash withdrawal).',
        }
