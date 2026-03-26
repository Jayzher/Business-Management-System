from django import forms
from django.forms import BaseInlineFormSet, inlineformset_factory
from catalog.models import Category, Unit, UnitCategory, UnitConversion, Item


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
        fields = ['name', 'abbreviation', 'category']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'abbreviation': forms.TextInput(attrs={'class': 'form-control'}),
            'category': forms.Select(attrs={'class': 'form-control'}),
        }
        help_texts = {
            'name': 'Full unit name (e.g. Piece, Kilogram, Meter).',
            'abbreviation': 'Short label used in tables and receipts (e.g. pcs, kg, m).',
            'category': 'Measurement category. Conversions are only allowed within the same category.',
        }


class UnitConversionForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound and (not getattr(self, 'instance', None) or not getattr(self.instance, 'pk', None)):
            self.fields['factor'].initial = None
            self.fields['conversion_price'].initial = None

    class Meta:
        model = UnitConversion
        fields = ['from_unit', 'to_unit', 'factor', 'conversion_price', 'item']
        widgets = {
            'from_unit': forms.Select(attrs={'class': 'form-control'}),
            'to_unit': forms.Select(attrs={'class': 'form-control'}),
            'factor': forms.NumberInput(attrs={
                'class': 'form-control', 'step': '0.000001', 'min': '0', 'placeholder': 'e.g., 20'
            }),
            'conversion_price': forms.NumberInput(attrs={
                'class': 'form-control', 'step': '0.01', 'min': '0',
                'placeholder': 'e.g., 30.00 (optional)',
            }),
            'item': forms.Select(attrs={'class': 'form-control select2'}),
        }
        help_texts = {
            'from_unit': 'Source unit (e.g. Roll).',
            'to_unit': 'Target unit (e.g. ft).',
            'factor': 'How many target units equal 1 source unit (e.g. 1 Roll = 5 ft → factor = 5).',
            'conversion_price': 'Optional explicit selling price per 1 to_unit. '
                                'If set, overrides factor-based price for selling (not COGS). '
                                'Example: leave item selling_price=100/Roll but charge 30/ft.',
            'item': 'Leave blank for a global conversion. Select a product to override for that specific item only.',
        }


class ItemUnitConversionForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound and (not getattr(self, 'instance', None) or not getattr(self.instance, 'pk', None)):
            self.fields['factor'].initial = None
            self.fields['conversion_price'].initial = None

    class Meta:
        model = UnitConversion
        fields = ['from_unit', 'to_unit', 'factor', 'conversion_price']
        widgets = {
            'from_unit': forms.Select(attrs={'class': 'form-control'}),
            'to_unit': forms.Select(attrs={'class': 'form-control'}),
            'factor': forms.NumberInput(attrs={
                'class': 'form-control', 'step': '0.000001', 'min': '0', 'placeholder': 'e.g., 5'
            }),
            'conversion_price': forms.NumberInput(attrs={
                'class': 'form-control', 'step': '0.01', 'min': '0',
                'placeholder': 'e.g., 30.00 (optional)',
            }),
        }
        help_texts = {
            'from_unit': 'Source unit for this item-specific conversion.',
            'to_unit': 'Target unit for this item-specific conversion.',
            'factor': 'How many target units equal 1 source unit.',
            'conversion_price': 'Optional explicit price per to_unit for selling. Leave blank to derive from item selling_price.',
        }


class BaseItemUnitConversionFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        seen = set()
        for form in self.forms:
            if not hasattr(form, 'cleaned_data'):
                continue
            if form.cleaned_data.get('DELETE'):
                continue
            from_unit = form.cleaned_data.get('from_unit')
            to_unit = form.cleaned_data.get('to_unit')
            factor = form.cleaned_data.get('factor')
            if not from_unit and not to_unit and factor in (None, ''):
                continue
            if from_unit and to_unit:
                key = (from_unit.pk, to_unit.pk)
                if key in seen:
                    raise forms.ValidationError('Duplicate conversion rows are not allowed for the same item.')
                seen.add(key)


ItemUnitConversionFormSet = inlineformset_factory(
    Item,
    UnitConversion,
    form=ItemUnitConversionForm,
    formset=BaseItemUnitConversionFormSet,
    extra=1,
    can_delete=True,
    fields=['from_unit', 'to_unit', 'factor', 'conversion_price'],
)


class ItemForm(forms.ModelForm):
    # Use 2 decimal places for prices on the form, even though the model stores 4
    cost_price = forms.DecimalField(
        max_digits=15,
        decimal_places=2,
        required=True,
        widget=forms.NumberInput(attrs={
            'class': 'form-control', 'step': '0.01', 'min': '0', 'placeholder': 'e.g., 150.00'
        }),
    )
    selling_price = forms.DecimalField(
        max_digits=15,
        decimal_places=2,
        required=True,
        widget=forms.NumberInput(attrs={
            'class': 'form-control', 'step': '0.01', 'min': '0', 'placeholder': 'e.g., 250.00'
        }),
    )
    minimum_stock = forms.DecimalField(
        max_digits=15,
        decimal_places=2,
        required=True,
        widget=forms.NumberInput(attrs={
            'class': 'form-control', 'step': '0.01', 'min': '0', 'placeholder': 'e.g., 10'
        }),
    )
    maximum_stock = forms.DecimalField(
        max_digits=15,
        decimal_places=2,
        required=True,
        widget=forms.NumberInput(attrs={
            'class': 'form-control', 'step': '0.01', 'min': '0', 'placeholder': 'e.g., 100'
        }),
    )
    reorder_point = forms.DecimalField(
        max_digits=15,
        decimal_places=2,
        required=True,
        widget=forms.NumberInput(attrs={
            'class': 'form-control', 'step': '0.01', 'min': '0', 'placeholder': 'e.g., 20'
        }),
    )

    def clean(self):
        return super().clean()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # For NEW items, show empty fields instead of 0.00
        if not self.is_bound and (not getattr(self, 'instance', None) or not getattr(self.instance, 'pk', None)):
            for name in ['cost_price', 'selling_price', 'minimum_stock', 'maximum_stock', 'reorder_point']:
                if name in self.fields:
                    self.fields[name].initial = None

        # For EDIT forms, format prices with exactly 2 decimals
        if not self.is_bound and getattr(self, 'instance', None) and getattr(self.instance, 'pk', None):
            for name in ['cost_price', 'selling_price']:
                if name in self.fields:
                    value = getattr(self.instance, name, None)
                    if value is not None:
                        # Coerce to string with 2 decimal places for display
                        self.initial[name] = f"{value:.2f}"
            for name in ['minimum_stock', 'maximum_stock', 'reorder_point']:
                if name in self.fields:
                    value = getattr(self.instance, name, None)
                    if value is not None:
                        self.initial[name] = f"{value:.2f}"

    class Meta:
        model = Item
        fields = [
            'code', 'name', 'item_type', 'category', 'default_unit', 'selling_unit',
            'description', 'barcode', 'cost_price', 'selling_price',
            'minimum_stock', 'maximum_stock', 'reorder_point', 'image',
        ]
        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'item_type': forms.Select(attrs={'class': 'form-control'}),
            'category': forms.Select(attrs={'class': 'form-control'}),
            'default_unit': forms.Select(attrs={'class': 'form-control'}),
            'selling_unit': forms.Select(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'barcode': forms.TextInput(attrs={'class': 'form-control'}),
            'cost_price': forms.NumberInput(attrs={
                'class': 'form-control', 'step': '0.01', 'min': '0', 'placeholder': 'e.g., 150.00'
            }),
            'selling_price': forms.NumberInput(attrs={
                'class': 'form-control', 'step': '0.01', 'min': '0', 'placeholder': 'e.g., 250.00'
            }),
            'minimum_stock': forms.NumberInput(attrs={
                'class': 'form-control', 'step': '1', 'min': '0', 'placeholder': 'e.g., 10'
            }),
            'maximum_stock': forms.NumberInput(attrs={
                'class': 'form-control', 'step': '1', 'min': '0', 'placeholder': 'e.g., 100'
            }),
            'reorder_point': forms.NumberInput(attrs={
                'class': 'form-control', 'step': '1', 'min': '0', 'placeholder': 'e.g., 20'
            }),
            'image': forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }
        help_texts = {
            'code': 'Unique product/material code (e.g. ALU-001, FIN-100).',
            'name': 'Descriptive item name shown in lists and receipts.',
            'item_type': 'Raw Material = used in production. Finished Product = sold to customers.',
            'category': 'Group items for filtering, reporting, and price list assignment.',
            'default_unit': 'Primary unit of measure for this item.',
            'selling_unit': 'Unit shown when selling (e.g., box, pack). Leave blank to use the base unit.',
            'barcode': 'Optional barcode or SKU for POS scanning.',
            'cost_price': 'Weighted average cost. Updated when posting GRNs.',
            'selling_price': 'Default selling price. Overridden by Price Lists when assigned.',
            'minimum_stock': 'Alert threshold — dashboard shows warning below this level.',
            'maximum_stock': 'Upper stock limit for reorder planning.',
            'reorder_point': 'System flags this item when total stock falls to this quantity.',
            'image': 'Optional product photo displayed on detail pages.',
        }
