from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from warehouses.models import Warehouse, Location
from warehouses.serializers import WarehouseSerializer, LocationSerializer
from warehouses.forms import WarehouseForm, LocationForm
from inventory.models import StockBalance
from inventory.serializers import StockBalanceSerializer


# ── API Views ──────────────────────────────────────────────────────────────

class WarehouseViewSet(viewsets.ModelViewSet):
    queryset = Warehouse.objects.all()
    serializer_class = WarehouseSerializer
    search_fields = ['code', 'name', 'city']
    filterset_fields = ['is_active']

    @action(detail=True, methods=['get'], url_path='stock-summary')
    def stock_summary(self, request, pk=None):
        warehouse = self.get_object()
        location_ids = warehouse.locations.values_list('id', flat=True)
        balances = StockBalance.objects.filter(
            location_id__in=location_ids, qty_on_hand__gt=0
        ).select_related('item', 'location')
        serializer = StockBalanceSerializer(balances, many=True)
        return Response(serializer.data)


class LocationViewSet(viewsets.ModelViewSet):
    queryset = Location.objects.select_related('warehouse', 'parent').all()
    serializer_class = LocationSerializer
    search_fields = ['code', 'name']
    filterset_fields = ['warehouse', 'location_type', 'is_pickable', 'is_active']


# ── Template Views ─────────────────────────────────────────────────────────

@login_required
def warehouse_list_view(request):
    warehouses = Warehouse.objects.all()
    return render(request, 'warehouses/warehouse_list.html', {'warehouses': warehouses})


@login_required
def location_list_view(request):
    locations = Location.objects.select_related('warehouse', 'parent').all()
    return render(request, 'warehouses/location_list.html', {'locations': locations})


@login_required
def warehouse_detail_view(request, pk):
    warehouse = get_object_or_404(Warehouse, pk=pk)
    locations = warehouse.locations.select_related('parent').all()
    location_ids = locations.values_list('id', flat=True)
    balances = StockBalance.objects.filter(
        location_id__in=location_ids, qty_on_hand__gt=0
    ).select_related('item', 'location')[:50]
    return render(request, 'warehouses/warehouse_detail.html', {
        'warehouse': warehouse,
        'locations': locations,
        'balances': balances,
    })


@login_required
def warehouse_create_view(request):
    if request.method == 'POST':
        form = WarehouseForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Warehouse created successfully.')
            return redirect('warehouse_list')
    else:
        form = WarehouseForm()
    return render(request, 'warehouses/warehouse_form.html', {'form': form, 'title': 'Create Warehouse'})


@login_required
def warehouse_edit_view(request, pk):
    warehouse = get_object_or_404(Warehouse, pk=pk)
    if request.method == 'POST':
        form = WarehouseForm(request.POST, instance=warehouse)
        if form.is_valid():
            form.save()
            messages.success(request, 'Warehouse updated successfully.')
            return redirect('warehouse_detail', pk=warehouse.pk)
    else:
        form = WarehouseForm(instance=warehouse)
    return render(request, 'warehouses/warehouse_form.html', {'form': form, 'title': f'Edit Warehouse: {warehouse.code}'})


@login_required
def warehouse_delete_view(request, pk):
    warehouse = get_object_or_404(Warehouse, pk=pk)
    if request.method == 'POST':
        warehouse.soft_delete()
        messages.success(request, f'Warehouse {warehouse.code} deleted.')
        return redirect('warehouse_list')
    return render(request, 'warehouses/warehouse_delete.html', {'object': warehouse})


# ── Location CRUD ──────────────────────────────────────────────────────────

@login_required
def location_create_view(request):
    warehouse_id = request.GET.get('warehouse')
    initial = {}
    if warehouse_id:
        initial['warehouse'] = warehouse_id
    if request.method == 'POST':
        form = LocationForm(request.POST)
        if form.is_valid():
            loc = form.save()
            messages.success(request, 'Location created successfully.')
            return redirect('warehouse_detail', pk=loc.warehouse.pk)
    else:
        form = LocationForm(initial=initial)
    return render(request, 'warehouses/location_form.html', {'form': form, 'title': 'Create Location'})


@login_required
def location_edit_view(request, pk):
    location = get_object_or_404(Location, pk=pk)
    if request.method == 'POST':
        form = LocationForm(request.POST, instance=location)
        if form.is_valid():
            form.save()
            messages.success(request, 'Location updated successfully.')
            return redirect('warehouse_detail', pk=location.warehouse.pk)
    else:
        form = LocationForm(instance=location)
    return render(request, 'warehouses/location_form.html', {'form': form, 'title': f'Edit Location: {location.code}'})


@login_required
def location_delete_view(request, pk):
    location = get_object_or_404(Location, pk=pk)
    wh_pk = location.warehouse.pk
    if request.method == 'POST':
        location.soft_delete()
        messages.success(request, f'Location {location.code} deleted.')
        return redirect('warehouse_detail', pk=wh_pk)
    return render(request, 'warehouses/location_delete.html', {'object': location, 'warehouse_pk': wh_pk})
