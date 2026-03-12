from django import forms
from django.forms import inlineformset_factory
from services.models import CustomerService, ServiceLine


class CustomerServiceForm(forms.ModelForm):
    class Meta:
        model = CustomerService
        fields = [
            'service_number', 'service_name', 'customer_name',
            'service_date', 'address', 'payment_status', 'amount',
            'warehouse', 'notes',
        ]
        widgets = {
            'service_number': forms.TextInput(attrs={
                'class': 'form-control form-control-sm',
                'placeholder': 'e.g., SVC-000001',
            }),
            'service_name': forms.TextInput(attrs={
                'class': 'form-control form-control-sm',
                'placeholder': 'e.g., AC Unit Repair',
            }),
            'customer_name': forms.TextInput(attrs={
                'class': 'form-control form-control-sm',
                'placeholder': 'Customer full name',
            }),
            'service_date': forms.DateInput(attrs={
                'class': 'form-control form-control-sm',
                'type': 'date',
            }),
            'address': forms.Textarea(attrs={
                'class': 'form-control form-control-sm',
                'rows': 2,
                'placeholder': 'Service address',
            }),
            'payment_status': forms.Select(attrs={'class': 'form-control form-control-sm'}),
            'amount': forms.NumberInput(attrs={
                'class': 'form-control form-control-sm',
                'step': '0.01', 'min': '0',
                'placeholder': 'Optional — overrides product line total',
            }),
            'warehouse': forms.Select(attrs={'class': 'form-control form-control-sm'}),
            'notes': forms.Textarea(attrs={
                'class': 'form-control form-control-sm',
                'rows': 2,
                'placeholder': 'Internal notes',
            }),
        }
        help_texts = {
            'service_number': 'Unique service job order number.',
            'service_name': 'Name / type of service being performed.',
            'customer_name': 'Customer name (plain text).',
            'service_date': 'Date the service is scheduled or performed.',
            'address': 'Service location address.',
            'payment_status': 'Current payment status.',
            'amount': 'Leave blank to use product line total.',
            'warehouse': 'Warehouse to deduct parts from on completion.',
            'notes': 'Internal remarks.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['amount'].required = False
        self.fields['warehouse'].required = False


class CustomerServiceEditForm(CustomerServiceForm):
    """Extended form shown only on Edit — adds completion_date."""
    class Meta(CustomerServiceForm.Meta):
        fields = CustomerServiceForm.Meta.fields + ['completion_date']
        widgets = {
            **CustomerServiceForm.Meta.widgets,
            'completion_date': forms.DateInput(attrs={
                'class': 'form-control form-control-sm',
                'type': 'date',
            }),
        }
        help_texts = {
            **CustomerServiceForm.Meta.help_texts,
            'completion_date': 'Date the service was completed.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['completion_date'].required = False


class ServiceLineForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound and (
            not getattr(self, 'instance', None) or
            not getattr(self.instance, 'pk', None)
        ):
            for name in ['qty', 'unit_price']:
                if name in self.fields:
                    self.fields[name].initial = None

    class Meta:
        model = ServiceLine
        fields = ['item', 'location', 'qty', 'unit', 'unit_price', 'notes']
        widgets = {
            'item': forms.Select(attrs={
                'class': 'form-control form-control-sm svc-line-item',
            }),
            'location': forms.Select(attrs={'class': 'form-control form-control-sm'}),
            'qty': forms.NumberInput(attrs={
                'class': 'form-control form-control-sm',
                'step': '0.01', 'min': '0', 'placeholder': 'e.g., 2',
            }),
            'unit': forms.Select(attrs={'class': 'form-control form-control-sm'}),
            'unit_price': forms.NumberInput(attrs={
                'class': 'form-control form-control-sm svc-line-price',
                'step': '0.01', 'min': '0',
                'placeholder': 'Auto-filled from catalog',
                'readonly': 'readonly',
            }),
            'notes': forms.TextInput(attrs={
                'class': 'form-control form-control-sm',
                'placeholder': 'Optional note',
            }),
        }
        help_texts = {
            'item': 'Part or item used in the service.',
            'location': 'Warehouse location to deduct from.',
            'qty': 'Quantity used.',
            'unit': 'Unit of measure.',
            'unit_price': 'Auto-filled from item selling price.',
            'notes': 'Optional line note.',
        }


ServiceLineFormSet = inlineformset_factory(
    CustomerService, ServiceLine,
    form=ServiceLineForm,
    extra=1, can_delete=True,
)
