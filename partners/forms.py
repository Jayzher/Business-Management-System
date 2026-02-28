from django import forms
from partners.models import Supplier, Customer


class SupplierForm(forms.ModelForm):
    class Meta:
        model = Supplier
        fields = ['code', 'name', 'contact_person', 'email', 'phone', 'address', 'city', 'notes']
        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'contact_person': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'city': forms.TextInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
        help_texts = {
            'code': 'Unique vendor code (e.g. SUP-001). Used on POs and GRNs.',
            'name': 'Legal or trade name of the supplier.',
            'contact_person': 'Primary contact for orders and inquiries.',
            'email': 'Email address for sending POs and correspondence.',
            'phone': 'Phone or mobile number.',
            'address': 'Full street address for delivery and billing.',
            'city': 'City or municipality.',
            'notes': 'Internal notes (payment terms, lead times, etc.).',
        }


class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = ['code', 'name', 'contact_person', 'email', 'phone', 'address', 'city', 'notes']
        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'contact_person': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'city': forms.TextInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
        help_texts = {
            'code': 'Unique customer code (e.g. CUS-001). Used on SOs and receipts.',
            'name': 'Customer or company name.',
            'contact_person': 'Primary contact for deliveries and invoices.',
            'email': 'Email for sending invoices and receipts.',
            'phone': 'Phone or mobile number.',
            'address': 'Delivery / billing address.',
            'city': 'City or municipality.',
            'notes': 'Internal notes (credit terms, special instructions, etc.).',
        }
