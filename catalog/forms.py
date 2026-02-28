from django import forms
from catalog.models import Category, Unit, UnitConversion, Item


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['code', 'name', 'parent', 'description']
        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'parent': forms.Select(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
        help_texts = {
            'code': 'Short unique code for this category (e.g. RAW, ALUM, GLASS).',
            'name': 'Display name shown in menus and reports.',
            'parent': 'Optional parent category to create a hierarchy.',
            'description': 'Optional notes about what this category covers.',
        }


class UnitForm(forms.ModelForm):
    class Meta:
        model = Unit
        fields = ['name', 'abbreviation']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'abbreviation': forms.TextInput(attrs={'class': 'form-control'}),
        }
        help_texts = {
            'name': 'Full unit name (e.g. Piece, Kilogram, Meter).',
            'abbreviation': 'Short label used in tables and receipts (e.g. pcs, kg, m).',
        }


class UnitConversionForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound and (not getattr(self, 'instance', None) or not getattr(self.instance, 'pk', None)):
            self.fields['factor'].initial = None

    class Meta:
        model = UnitConversion
        fields = ['from_unit', 'to_unit', 'factor']
        widgets = {
            'from_unit': forms.Select(attrs={'class': 'form-control'}),
            'to_unit': forms.Select(attrs={'class': 'form-control'}),
            'factor': forms.NumberInput(attrs={
                'class': 'form-control', 'step': '0.000001', 'placeholder': 'e.g., 20'
            }),
        }
        help_texts = {
            'from_unit': 'Source unit (e.g. Box).',
            'to_unit': 'Target unit (e.g. Piece).',
            'factor': 'How many target units equal 1 source unit (e.g. 1 Box = 20 pcs → factor = 20).',
        }


class ItemForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound and (not getattr(self, 'instance', None) or not getattr(self.instance, 'pk', None)):
            for name in ['cost_price', 'selling_price', 'minimum_stock', 'maximum_stock', 'reorder_point']:
                if name in self.fields:
                    self.fields[name].initial = None

    class Meta:
        model = Item
        fields = [
            'code', 'name', 'item_type', 'category', 'default_unit',
            'description', 'barcode', 'cost_price', 'selling_price',
            'minimum_stock', 'maximum_stock', 'reorder_point', 'image',
        ]
        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'item_type': forms.Select(attrs={'class': 'form-control'}),
            'category': forms.Select(attrs={'class': 'form-control'}),
            'default_unit': forms.Select(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'barcode': forms.TextInput(attrs={'class': 'form-control'}),
            'cost_price': forms.NumberInput(attrs={
                'class': 'form-control', 'step': '0.01', 'placeholder': 'e.g., 150.00'
            }),
            'selling_price': forms.NumberInput(attrs={
                'class': 'form-control', 'step': '0.01', 'placeholder': 'e.g., 250.00'
            }),
            'minimum_stock': forms.NumberInput(attrs={
                'class': 'form-control', 'step': '0.0001', 'placeholder': 'e.g., 10'
            }),
            'maximum_stock': forms.NumberInput(attrs={
                'class': 'form-control', 'step': '0.0001', 'placeholder': 'e.g., 100'
            }),
            'reorder_point': forms.NumberInput(attrs={
                'class': 'form-control', 'step': '0.0001', 'placeholder': 'e.g., 20'
            }),
            'image': forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }
        help_texts = {
            'code': 'Unique product/material code (e.g. ALU-001, FIN-100).',
            'name': 'Descriptive item name shown in lists and receipts.',
            'item_type': 'Raw Material = used in production. Finished Product = sold to customers.',
            'category': 'Group items for filtering, reporting, and price list assignment.',
            'default_unit': 'Primary unit of measure for this item.',
            'barcode': 'Optional barcode or SKU for POS scanning.',
            'cost_price': 'Weighted average cost. Updated when posting GRNs.',
            'selling_price': 'Default selling price. Overridden by Price Lists when assigned.',
            'minimum_stock': 'Alert threshold — dashboard shows warning below this level.',
            'maximum_stock': 'Upper stock limit for reorder planning.',
            'reorder_point': 'System flags this item when total stock falls to this quantity.',
            'image': 'Optional product photo displayed on detail pages.',
        }
