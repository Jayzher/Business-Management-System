from django import forms
from cashflow.models import CashFlowTransaction


class CashFlowTransactionForm(forms.ModelForm):
    class Meta:
        model = CashFlowTransaction
        fields = [
            'category', 'flow_type', 'amount', 'transaction_date',
            'payment_method', 'reference_no', 'reason', 'notes',
        ]
        widgets = {
            'category': forms.Select(attrs={'class': 'form-control'}),
            'flow_type': forms.Select(attrs={'class': 'form-control'}),
            'amount': forms.NumberInput(attrs={
                'class': 'form-control', 'step': '0.01', 'min': '0.01',
                'placeholder': '0.00',
            }),
            'transaction_date': forms.DateInput(attrs={
                'class': 'form-control', 'type': 'date',
            }),
            'payment_method': forms.Select(attrs={'class': 'form-control'}),
            'reference_no': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': 'e.g. receipt #, check #',
            }),
            'reason': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': 'Purpose of this transaction',
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 3,
                'placeholder': 'Additional notes (optional)',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            import datetime
            self.fields['transaction_date'].initial = datetime.date.today().isoformat()


class CashFlowRejectForm(forms.Form):
    """Small form for the rejection reason."""
    rejection_reason = forms.CharField(
        max_length=300,
        widget=forms.Textarea(attrs={
            'class': 'form-control', 'rows': 2,
            'placeholder': 'Reason for rejection',
        }),
        help_text='Explain why this transaction is being rejected.',
    )
