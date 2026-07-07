from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from rest_framework import viewsets

from partners.models import Supplier, Customer
from partners.serializers import SupplierSerializer, CustomerSerializer
from partners.forms import SupplierForm, CustomerForm
from accounts.decorators import write_denied_for_viewer


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

SUPPLIER_CUSTOMER_SORT_MAP = {
    'code': 'code',
    'name': 'name',
    'contact': 'contact_person',
    'email': 'email',
    'phone': 'phone',
    'city': 'city',
    'status': 'is_active',
}


@login_required
def supplier_list_view(request):
    from core.utils import sort_queryset, paginate_queryset, search_queryset
    suppliers = Supplier.objects.all()
    suppliers = search_queryset(request, suppliers, [
        'code', 'name', 'contact_person', 'email', 'phone', 'city',
    ])
    status_filter = (request.GET.get('status') or '').strip()
    if status_filter:
        suppliers = suppliers.filter(is_active=(status_filter == '1'))
    suppliers, sort, direction = sort_queryset(
        request, suppliers, SUPPLIER_CUSTOMER_SORT_MAP, default_key='created_at', default_dir='desc'
    )
    page_obj = paginate_queryset(request, suppliers, per_page=25)
    filters = [{
        'param': 'status',
        'label': 'Status',
        'options': [('1', 'Active'), ('0', 'Inactive')],
    }]
    return render(request, 'partners/supplier_list.html', {
        'suppliers': page_obj,
        'page_obj': page_obj,
        'sort': sort,
        'dir': direction,
        'filters': filters,
    })


@login_required
@write_denied_for_viewer
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
@write_denied_for_viewer
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
@write_denied_for_viewer
def supplier_delete_view(request, pk):
    supplier = get_object_or_404(Supplier, pk=pk)
    if request.method == 'POST':
        supplier.soft_delete()
        messages.success(request, f'Supplier {supplier.code} deleted.')
        return redirect('supplier_list')
    return render(request, 'partners/supplier_delete.html', {'object': supplier})


@login_required
def customer_list_view(request):
    from core.utils import sort_queryset, paginate_queryset, search_queryset
    customers = Customer.objects.all()
    customers = search_queryset(request, customers, [
        'code', 'name', 'contact_person', 'email', 'phone', 'city',
    ])
    status_filter = (request.GET.get('status') or '').strip()
    if status_filter:
        customers = customers.filter(is_active=(status_filter == '1'))
    customers, sort, direction = sort_queryset(
        request, customers, SUPPLIER_CUSTOMER_SORT_MAP, default_key='created_at', default_dir='desc'
    )
    page_obj = paginate_queryset(request, customers, per_page=25)
    filters = [{
        'param': 'status',
        'label': 'Status',
        'options': [('1', 'Active'), ('0', 'Inactive')],
    }]
    return render(request, 'partners/customer_list.html', {
        'customers': page_obj,
        'page_obj': page_obj,
        'sort': sort,
        'dir': direction,
        'filters': filters,
    })


@login_required
@write_denied_for_viewer
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
@write_denied_for_viewer
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
@write_denied_for_viewer
def customer_delete_view(request, pk):
    customer = get_object_or_404(Customer, pk=pk)
    if request.method == 'POST':
        customer.soft_delete()
        messages.success(request, f'Customer {customer.code} deleted.')
        return redirect('customer_list')
    return render(request, 'partners/customer_delete.html', {'object': customer})
