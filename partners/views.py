from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from rest_framework import viewsets

from partners.models import Supplier, Customer
from partners.serializers import SupplierSerializer, CustomerSerializer
from partners.forms import SupplierForm, CustomerForm


# ── API Views ──────────────────────────────────────────────────────────────

class SupplierViewSet(viewsets.ModelViewSet):
    queryset = Supplier.objects.all()
    serializer_class = SupplierSerializer
    search_fields = ['code', 'name', 'contact_person', 'email']
    filterset_fields = ['is_active', 'city']


class CustomerViewSet(viewsets.ModelViewSet):
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer
    search_fields = ['code', 'name', 'contact_person', 'email']
    filterset_fields = ['is_active', 'city']


# ── Template Views ─────────────────────────────────────────────────────────

@login_required
def supplier_list_view(request):
    suppliers = Supplier.objects.all()
    return render(request, 'partners/supplier_list.html', {'suppliers': suppliers})


@login_required
def supplier_create_view(request):
    if request.method == 'POST':
        form = SupplierForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Supplier created successfully.')
            return redirect('supplier_list')
    else:
        form = SupplierForm()
    return render(request, 'partners/supplier_form.html', {'form': form, 'title': 'Create Supplier'})


@login_required
def supplier_edit_view(request, pk):
    supplier = get_object_or_404(Supplier, pk=pk)
    if request.method == 'POST':
        form = SupplierForm(request.POST, instance=supplier)
        if form.is_valid():
            form.save()
            messages.success(request, 'Supplier updated successfully.')
            return redirect('supplier_list')
    else:
        form = SupplierForm(instance=supplier)
    return render(request, 'partners/supplier_form.html', {'form': form, 'title': f'Edit Supplier: {supplier.code}'})


@login_required
def supplier_delete_view(request, pk):
    supplier = get_object_or_404(Supplier, pk=pk)
    if request.method == 'POST':
        supplier.soft_delete()
        messages.success(request, f'Supplier {supplier.code} deleted.')
        return redirect('supplier_list')
    return render(request, 'partners/supplier_delete.html', {'object': supplier})


@login_required
def customer_list_view(request):
    customers = Customer.objects.all()
    return render(request, 'partners/customer_list.html', {'customers': customers})


@login_required
def customer_create_view(request):
    if request.method == 'POST':
        form = CustomerForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Customer created successfully.')
            return redirect('customer_list')
    else:
        form = CustomerForm()
    return render(request, 'partners/customer_form.html', {'form': form, 'title': 'Create Customer'})


@login_required
def customer_edit_view(request, pk):
    customer = get_object_or_404(Customer, pk=pk)
    if request.method == 'POST':
        form = CustomerForm(request.POST, instance=customer)
        if form.is_valid():
            form.save()
            messages.success(request, 'Customer updated successfully.')
            return redirect('customer_list')
    else:
        form = CustomerForm(instance=customer)
    return render(request, 'partners/customer_form.html', {'form': form, 'title': f'Edit Customer: {customer.code}'})


@login_required
def customer_delete_view(request, pk):
    customer = get_object_or_404(Customer, pk=pk)
    if request.method == 'POST':
        customer.soft_delete()
        messages.success(request, f'Customer {customer.code} deleted.')
        return redirect('customer_list')
    return render(request, 'partners/customer_delete.html', {'object': customer})
