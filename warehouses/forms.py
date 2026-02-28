from django import forms
from warehouses.models import Warehouse, Location


class WarehouseForm(forms.ModelForm):
    class Meta:
        model = Warehouse
        fields = ['code', 'name', 'address', 'city', 'phone', 'manager', 'allow_negative_stock']
        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'city': forms.TextInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'manager': forms.Select(attrs={'class': 'form-control'}),
            'allow_negative_stock': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        help_texts = {
            'code': 'Short unique warehouse code (e.g. WH-MAIN, WH-POS).',
            'name': 'Descriptive name for this warehouse.',
            'address': 'Physical street address.',
            'city': 'City or municipality where the warehouse is located.',
            'phone': 'Contact phone for this warehouse.',
            'manager': 'User responsible for this warehouse.',
            'allow_negative_stock': 'If checked, stock can go below zero (use with caution).',
        }


class LocationForm(forms.ModelForm):
    class Meta:
        model = Location
        fields = ['warehouse', 'code', 'name', 'parent', 'location_type', 'is_pickable']
        widgets = {
            'warehouse': forms.Select(attrs={'class': 'form-control'}),
            'code': forms.TextInput(attrs={'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'parent': forms.Select(attrs={'class': 'form-control'}),
            'location_type': forms.Select(attrs={'class': 'form-control'}),
            'is_pickable': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        help_texts = {
            'warehouse': 'The warehouse this location belongs to.',
            'code': 'Location code unique within its warehouse (e.g. A-01-01).',
            'name': 'Human-readable location name.',
            'parent': 'Optional parent location to build Zone > Aisle > Rack > Bin hierarchy.',
            'location_type': 'Zone = area, Aisle = row, Rack = shelf, Bin = specific slot.',
            'is_pickable': 'If checked, items can be picked/sold from this location in POS and deliveries.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['parent'].queryset = Location.objects.select_related('warehouse').all()
        self.fields['parent'].required = False


