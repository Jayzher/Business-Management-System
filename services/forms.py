from django import forms
from django.forms import inlineformset_factory
from services.models import CustomerService, ServiceLine, ServiceOtherMaterial, ServiceBundle, ServicePaymentStatus

_SM = 'form-control form-control-sm'
_NUM = {'class': _SM, 'step': '0.01', 'min': '0'}


class CustomerServiceForm(forms.ModelForm):
    class Meta:
        model = CustomerService
        fields = [
            'service_number', 'service_name', 'customer_name',
            'service_date', 'address', 'payment_status', 'partial_payment_amount',
            'quotation', 'discount_type', 'discount_value',
            'warehouse', 'notes',
        ]
        widgets = {
            'service_number': forms.TextInput(attrs={'class': _SM, 'placeholder': 'e.g., SVC-000001'}),
            'service_name': forms.TextInput(attrs={'class': _SM, 'placeholder': 'e.g., AC Unit Repair'}),
            'customer_name': forms.TextInput(attrs={'class': _SM, 'placeholder': 'Customer full name'}),
            'service_date': forms.DateInput(attrs={'class': _SM, 'type': 'date'}),
            'address': forms.Textarea(attrs={'class': _SM, 'rows': 2, 'placeholder': 'Service address'}),
            'payment_status': forms.Select(attrs={'class': _SM, 'id': 'id_payment_status'}),
            'partial_payment_amount': forms.NumberInput(attrs={**_NUM, 'placeholder': '0.00', 'id': 'id_partial_payment_amount'}),
            'quotation': forms.NumberInput(attrs={**_NUM, 'placeholder': '0.00', 'id': 'id_quotation'}),
            'discount_type': forms.Select(attrs={'class': _SM, 'id': 'id_discount_type'}),
            'discount_value': forms.NumberInput(attrs={**_NUM, 'placeholder': '0.00', 'id': 'id_discount_value'}),
            'warehouse': forms.Select(attrs={'class': _SM}),
            'notes': forms.Textarea(attrs={'class': _SM, 'rows': 2, 'placeholder': 'Internal notes'}),
        }
        help_texts = {
            'service_number': 'Unique service job order number.',
            'service_name': 'Name / type of service being performed.',
            'customer_name': 'Customer name (plain text).',
            'service_date': 'Date the service is scheduled or performed.',
            'address': 'Service location address.',
            'payment_status': 'Current payment status.',
            'partial_payment_amount': 'Required when payment status is Partially Paid.',
            'quotation': 'Total amount quoted to the customer for this service.',
            'discount_type': 'How the discount is applied.',
            'discount_value': 'Discount amount or percentage.',
            'warehouse': 'Warehouse to deduct parts from on completion.',
            'notes': 'Internal remarks.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['quotation'].required = False
        self.fields['warehouse'].required = False
        self.fields['discount_value'].required = False
        self.fields['partial_payment_amount'].required = False

    def clean(self):
        cleaned_data = super().clean()
        payment_status = cleaned_data.get('payment_status')
        partial_payment_amount = cleaned_data.get('partial_payment_amount')
        quotation = cleaned_data.get('quotation') or 0

        if payment_status == ServicePaymentStatus.PARTIAL:
            if partial_payment_amount in (None, ''):
                self.add_error('partial_payment_amount', 'Enter the partial payment amount.')
            elif partial_payment_amount <= 0:
                self.add_error('partial_payment_amount', 'Partial payment amount must be greater than 0.')
            elif quotation and partial_payment_amount > quotation:
                self.add_error('partial_payment_amount', 'Partial payment amount cannot exceed the quotation amount.')
        elif payment_status == ServicePaymentStatus.PAID:
            cleaned_data['partial_payment_amount'] = quotation
        else:
            cleaned_data['partial_payment_amount'] = 0

        return cleaned_data


class CustomerServiceEditForm(CustomerServiceForm):
    """Extended form shown only on Edit — adds completion_date."""
    class Meta(CustomerServiceForm.Meta):
        fields = CustomerServiceForm.Meta.fields + ['completion_date']
        widgets = {
            **CustomerServiceForm.Meta.widgets,
            'completion_date': forms.DateInput(attrs={'class': _SM, 'type': 'date'}),
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
            'item': forms.Select(attrs={'class': f'{_SM} svc-line-item'}),
            'location': forms.Select(attrs={'class': _SM}),
            'qty': forms.NumberInput(attrs={**_NUM, 'placeholder': 'e.g., 2'}),
            'unit': forms.Select(attrs={'class': f'{_SM} svc-line-unit bg-light', 'style': 'pointer-events:none;', 'tabindex': '-1', 'aria-readonly': 'true'}),
            'unit_price': forms.NumberInput(attrs={**_NUM, 'class': f'{_SM} svc-line-price bg-light', 'placeholder': 'Selling price (auto-filled)', 'readonly': 'readonly'}),
            'notes': forms.TextInput(attrs={'class': _SM, 'placeholder': 'Optional note'}),
        }
        help_texts = {
            'item': 'Part or item used in the service.',
            'location': 'Warehouse location to deduct from.',
            'qty': 'Quantity used.',
            'unit': 'Unit of measure.',
            'unit_price': 'Selling price per unit (auto-filled from catalog).',
            'notes': 'Optional line note.',
        }


ServiceLineFormSet = inlineformset_factory(
    CustomerService, ServiceLine,
    form=ServiceLineForm,
    extra=1, can_delete=True,
)


class ServiceOtherMaterialForm(forms.ModelForm):
    class Meta:
        model = ServiceOtherMaterial
        fields = ['item_name', 'qty', 'unit_price', 'vendor', 'notes']
        widgets = {
            'item_name': forms.TextInput(attrs={'class': _SM, 'placeholder': 'e.g., Copper wire, Epoxy resin'}),
            'qty': forms.NumberInput(attrs={**_NUM, 'placeholder': '1', 'class': f'{_SM} mat-qty'}),
            'unit_price': forms.NumberInput(attrs={**_NUM, 'placeholder': '0.00', 'class': f'{_SM} mat-price'}),
            'vendor': forms.TextInput(attrs={'class': _SM, 'placeholder': 'Supplier / vendor name'}),
            'notes': forms.TextInput(attrs={'class': _SM, 'placeholder': 'Optional note'}),
        }
        help_texts = {
            'item_name': 'Free-text description of the material.',
            'qty': 'Quantity consumed.',
            'unit_price': 'Price charged to the customer per unit.',
            'vendor': 'Optional vendor / supplier name.',
            'notes': 'Optional note.',
        }


ServiceOtherMaterialFormSet = inlineformset_factory(
    CustomerService, ServiceOtherMaterial,
    form=ServiceOtherMaterialForm,
    extra=1, can_delete=True,
)


class ServiceBundleForm(forms.ModelForm):
    class Meta:
        model = ServiceBundle
        fields = ['price_list', 'qty']
        widgets = {
            'price_list': forms.Select(attrs={
                'class': f'{_SM} svc-bundle-pricelist',
            }),
            'qty': forms.NumberInput(attrs={
                'class': f'{_SM} svc-bundle-qty',
                'step': '1', 'min': '1', 'placeholder': '1',
                'style': 'width:70px;',
            }),
        }


ServiceBundleFormSet = inlineformset_factory(
    CustomerService, ServiceBundle,
    form=ServiceBundleForm,
    extra=0, can_delete=True,
)
