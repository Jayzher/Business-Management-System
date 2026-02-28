from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import ProtectedError
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from catalog.models import Category, Unit, UnitConversion, Item
from core.utils import (
    build_relation_summary,
    handle_delete_error,
    handle_delete_success,
    handle_protected_error,
    format_in_use_message,
)
from catalog.serializers import (
    CategorySerializer, UnitSerializer, UnitConversionSerializer,
    ItemSerializer, ItemListSerializer,
)
from catalog.forms import CategoryForm, UnitForm, UnitConversionForm, ItemForm
from inventory.models import StockBalance
from inventory.serializers import StockBalanceSerializer


# ── API Views ──────────────────────────────────────────────────────────────

class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    search_fields = ['name', 'code']
    filterset_fields = ['parent', 'is_active']


class UnitViewSet(viewsets.ModelViewSet):
    queryset = Unit.objects.all()
    serializer_class = UnitSerializer
    search_fields = ['name', 'abbreviation']


class UnitConversionViewSet(viewsets.ModelViewSet):
    queryset = UnitConversion.objects.select_related('from_unit', 'to_unit').all()
    serializer_class = UnitConversionSerializer


class ItemViewSet(viewsets.ModelViewSet):
    queryset = Item.objects.select_related('category', 'default_unit').all()
    search_fields = ['code', 'name', 'barcode']
    filterset_fields = ['item_type', 'category', 'is_active']

    def get_serializer_class(self):
        if self.action == 'list':
            return ItemListSerializer
        return ItemSerializer

    @action(detail=True, methods=['get'])
    def stock(self, request, pk=None):
        item = self.get_object()
        balances = StockBalance.objects.filter(
            item=item, qty_on_hand__gt=0
        ).select_related('location', 'location__warehouse')
        serializer = StockBalanceSerializer(balances, many=True)
        return Response(serializer.data)


# ── Template Views ─────────────────────────────────────────────────────────

@login_required
def item_list_view(request):
    items = Item.objects.select_related('category', 'default_unit').all()
    item_type = request.GET.get('type')
    category_id = request.GET.get('category')
    search = request.GET.get('q')
    if item_type:
        items = items.filter(item_type=item_type)
    if category_id:
        items = items.filter(category_id=category_id)
    if search:
        items = items.filter(name__icontains=search) | items.filter(code__icontains=search)
    categories = Category.objects.filter(is_active=True)
    return render(request, 'catalog/item_list.html', {
        'items': items,
        'categories': categories,
        'current_type': item_type,
        'current_category': category_id,
        'search': search or '',
    })


@login_required
def item_detail_view(request, pk):
    from decimal import Decimal
    from django.db.models import Sum
    from django.db.models.functions import Coalesce
    item = get_object_or_404(Item, pk=pk)
    balances = StockBalance.objects.filter(
        item=item
    ).select_related('location', 'location__warehouse')

    # Aggregate totals per warehouse
    warehouse_summary = balances.values(
        'location__warehouse__code', 'location__warehouse__name'
    ).annotate(
        total_on_hand=Coalesce(Sum('qty_on_hand'), Decimal('0')),
        total_reserved=Coalesce(Sum('qty_reserved'), Decimal('0')),
    ).order_by('location__warehouse__code')

    # Grand totals
    totals = balances.aggregate(
        total_on_hand=Coalesce(Sum('qty_on_hand'), Decimal('0')),
        total_reserved=Coalesce(Sum('qty_reserved'), Decimal('0')),
    )
    totals['total_available'] = totals['total_on_hand'] - totals['total_reserved']
    totals['total_value'] = totals['total_on_hand'] * (item.cost_price or Decimal('0'))

    from inventory.models import StockMove
    recent_moves = StockMove.objects.filter(
        item=item, status='POSTED'
    ).select_related('unit', 'from_location', 'to_location', 'created_by')[:20]
    return render(request, 'catalog/item_detail.html', {
        'item': item,
        'balances': balances,
        'warehouse_summary': warehouse_summary,
        'totals': totals,
        'recent_moves': recent_moves,
    })


@login_required
def item_create_view(request):
    if request.method == 'POST':
        form = ItemForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, 'Item created successfully.')
            return redirect('item_list')
    else:
        form = ItemForm()
    return render(request, 'catalog/item_form.html', {'form': form, 'title': 'Create Item'})


@login_required
def item_edit_view(request, pk):
    item = get_object_or_404(Item, pk=pk)
    if request.method == 'POST':
        form = ItemForm(request.POST, request.FILES, instance=item)
        if form.is_valid():
            form.save()
            messages.success(request, 'Item updated successfully.')
            return redirect('item_detail', pk=item.pk)
    else:
        form = ItemForm(instance=item)
    return render(request, 'catalog/item_form.html', {'form': form, 'title': f'Edit Item: {item.code}'})


@login_required
def item_delete_view(request, pk):
    item = get_object_or_404(Item, pk=pk)
    if request.method == 'POST':
        item.soft_delete()
        messages.success(request, f'Item {item.code} deleted.')
        return redirect('item_list')
    return render(request, 'catalog/item_delete.html', {'object': item})


# ── Category CRUD ──────────────────────────────────────────────────────────

@login_required
def category_list_view(request):
    categories = Category.objects.all()
    return render(request, 'catalog/category_list.html', {'categories': categories})


@login_required
def category_create_view(request):
    if request.method == 'POST':
        form = CategoryForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Category created successfully.')
            return redirect('category_list')
    else:
        form = CategoryForm()
    return render(request, 'catalog/category_form.html', {'form': form, 'title': 'Create Category'})


@login_required
def category_edit_view(request, pk):
    category = get_object_or_404(Category, pk=pk)
    if request.method == 'POST':
        form = CategoryForm(request.POST, instance=category)
        if form.is_valid():
            form.save()
            messages.success(request, 'Category updated successfully.')
            return redirect('category_list')
    else:
        form = CategoryForm(instance=category)
    return render(request, 'catalog/category_form.html', {'form': form, 'title': f'Edit Category: {category.name}'})


@login_required
def category_delete_view(request, pk):
    category = get_object_or_404(Category, pk=pk)
    relation_summary = build_relation_summary(category)
    if request.method == 'POST':
        try:
            if category.children.exists() or category.items.exists():
                base_msg = 'Cannot delete category because it is in use or referenced by other records.'
                response = handle_delete_error(request, base_msg, relation_summary)
                if response:
                    return response
            else:
                name = category.name
                category.delete()
                msg = f'Category {name} deleted.'
                response = handle_delete_success(request, msg)
                if response:
                    return response
                return redirect('category_list')
        except ProtectedError as e:
            base_msg = 'Cannot delete category because it is in use or referenced by other records.'
            response = handle_protected_error(request, e, base_msg, relation_summary)
            if response:
                return response
    return render(request, 'catalog/category_delete.html', {'object': category, 'relation_summary': relation_summary})

# ── Unit CRUD ──────────────────────────────────────────────────────────────

@login_required
def unit_list_view(request):
    units = Unit.objects.all()
    return render(request, 'catalog/unit_list.html', {'units': units})

@login_required
def unit_create_view(request):
    if request.method == 'POST':
        form = UnitForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Unit created successfully.')
            return redirect('unit_list')
    else:
        form = UnitForm()
    return render(request, 'catalog/unit_form.html', {'form': form, 'title': 'Create Unit'})


@login_required
def unit_edit_view(request, pk):
    unit = get_object_or_404(Unit, pk=pk)
    if request.method == 'POST':
        form = UnitForm(request.POST, instance=unit)
        if form.is_valid():
            form.save()
            messages.success(request, 'Unit updated successfully.')
            return redirect('unit_list')
    else:
        form = UnitForm(instance=unit)
    return render(request, 'catalog/unit_form.html', {'form': form, 'title': f'Edit Unit: {unit.name}'})


@login_required
def unit_delete_view(request, pk):
    unit = get_object_or_404(Unit, pk=pk)
    if request.method == 'POST':
        unit.soft_delete()
        messages.success(request, f'Unit {unit.name} deleted.')
        return redirect('unit_list')
    return render(request, 'catalog/unit_delete.html', {'object': unit})
