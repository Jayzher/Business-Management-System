from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q
from rest_framework import viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from pricing.models import PriceList, PriceListItem, DiscountRule, CustomerPriceCatalog, CustomerPriceCatalogItem
from pricing.serializers import PriceListSerializer, PriceListItemSerializer, DiscountRuleSerializer
from pricing.forms import (
    PriceListForm, PriceListItemFormSet, DiscountRuleForm,
    CustomerPriceCatalogForm, CustomerPriceCatalogItemFormSet,
)


# ── API Views ──────────────────────────────────────────────────────────────

class PriceListViewSet(viewsets.ModelViewSet):
    queryset = PriceList.objects.select_related('warehouse').prefetch_related('items').all()
    serializer_class = PriceListSerializer
    filterset_fields = ['warehouse', 'is_default', 'is_active']
    search_fields = ['name']


class PriceListItemViewSet(viewsets.ModelViewSet):
    queryset = PriceListItem.objects.select_related('price_list', 'item', 'unit').all()
    serializer_class = PriceListItemSerializer
    filterset_fields = ['price_list', 'item']


class DiscountRuleViewSet(viewsets.ModelViewSet):
    queryset = DiscountRule.objects.all()
    serializer_class = DiscountRuleSerializer
    filterset_fields = ['discount_type', 'scope', 'is_active']


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def bundle_items(request, pk):
    """
    Return all PriceListItems for a PriceList (bundle/package).
    Used by the SO bundle preview modal.
    """
    pl = get_object_or_404(PriceList, pk=pk)
    items = (
        PriceListItem.objects
        .filter(price_list=pl)
        .select_related('item', 'unit', 'item__category')
        .order_by('item__code')
    )
    data = {
        'id': pl.pk,
        'name': pl.name,
        'currency': pl.currency,
        'items': [
            {
                'id': pli.pk,
                'item_id': pli.item_id,
                'item_code': pli.item.code,
                'item_name': pli.item.name,
                'item_image': pli.item.image.url if pli.item.image else None,
                'unit_id': pli.unit_id,
                'unit_abbr': pli.unit.abbreviation,
                'price': str(pli.price),
                'min_qty': str(pli.min_qty),
                'catalog_price': str(pli.item.selling_price),
            }
            for pli in items
        ],
    }
    return Response(data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def price_lookup(request):
    """
    Look up the best price for an item.
    Query params: item, qty, unit, register (optional)
    """
    from pos.models import POSRegister

    item_id = request.query_params.get('item')
    qty = request.query_params.get('qty', '1')
    unit_id = request.query_params.get('unit')
    register_id = request.query_params.get('register')

    if not item_id:
        return Response({'error': 'item is required'}, status=400)

    today = timezone.now().date()
    filters = {
        'item_id': item_id,
        'price_list__is_active': True,
    }
    if unit_id:
        filters['unit_id'] = unit_id

    # If register provided, try register's price list first
    if register_id:
        try:
            reg = POSRegister.objects.get(pk=register_id)
            if reg.price_list_id:
                reg_prices = PriceListItem.objects.filter(
                    price_list=reg.price_list, item_id=item_id,
                ).filter(
                    models_q_date_range(today)
                ).order_by('-min_qty')
                for p in reg_prices:
                    if float(qty) >= float(p.min_qty):
                        return Response({
                            'price': str(p.price),
                            'unit': p.unit_id,
                            'price_list': p.price_list.name,
                        })
        except POSRegister.DoesNotExist:
            pass

    # Fall back to default price list
    from django.db.models import Q
    qs = PriceListItem.objects.filter(**filters).filter(
        Q(start_date__isnull=True) | Q(start_date__lte=today),
        Q(end_date__isnull=True) | Q(end_date__gte=today),
        price_list__is_active=True,
    ).select_related('price_list').order_by('price_list__is_default', '-min_qty')

    for p in qs:
        if float(qty) >= float(p.min_qty):
            return Response({
                'price': str(p.price),
                'unit': p.unit_id,
                'price_list': p.price_list.name,
            })

    return Response({'price': None, 'message': 'No price found'})


def models_q_date_range(today):
    from django.db.models import Q
    return (
        Q(start_date__isnull=True) | Q(start_date__lte=today)
    ) & (
        Q(end_date__isnull=True) | Q(end_date__gte=today)
    )


# ── Template Views ─────────────────────────────────────────────────────────

@login_required
def price_list_list_view(request):
    price_lists = PriceList.objects.select_related('warehouse').all()
    return render(request, 'pricing/price_list_list.html', {'price_lists': price_lists})


@login_required
def price_list_create_view(request):
    if request.method == 'POST':
        form = PriceListForm(request.POST)
        formset = PriceListItemFormSet(request.POST)
        if form.is_valid():
            obj = form.save()
            formset = PriceListItemFormSet(request.POST, instance=obj)
            if formset.is_valid():
                formset.save()
                messages.success(request, f'Price List "{obj.name}" created.')
                return redirect('price_list_list')
    else:
        form = PriceListForm()
        formset = PriceListItemFormSet()
    return render(request, 'pricing/price_list_form.html', {
        'form': form, 'formset': formset, 'title': 'Create Price List',
    })


@login_required
def price_list_edit_view(request, pk):
    obj = get_object_or_404(PriceList, pk=pk)
    if request.method == 'POST':
        form = PriceListForm(request.POST, instance=obj)
        formset = PriceListItemFormSet(request.POST, instance=obj)
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            messages.success(request, f'Price List "{obj.name}" updated.')
            return redirect('price_list_list')
    else:
        form = PriceListForm(instance=obj)
        formset = PriceListItemFormSet(instance=obj)
    return render(request, 'pricing/price_list_form.html', {
        'form': form, 'formset': formset, 'title': f'Edit Price List: {obj.name}',
    })


@login_required
def price_list_delete_view(request, pk):
    obj = get_object_or_404(PriceList, pk=pk)
    if request.method == 'POST':
        obj.soft_delete()
        messages.success(request, f'Price List "{obj.name}" deleted.')
        return redirect('price_list_list')
    return render(request, 'pricing/price_list_delete.html', {'object': obj})


# ── Discount Rule Template Views ──────────────────────────────────────────

@login_required
def discount_rule_list_view(request):
    rules = DiscountRule.objects.filter(is_active=True)
    return render(request, 'pricing/discount_rule_list.html', {'rules': rules})


@login_required
def discount_rule_create_view(request):
    if request.method == 'POST':
        form = DiscountRuleForm(request.POST)
        if form.is_valid():
            obj = form.save()
            messages.success(request, f'Discount Rule "{obj.name}" created.')
            return redirect('discount_rule_list')
    else:
        form = DiscountRuleForm()
    return render(request, 'pricing/discount_rule_form.html', {
        'form': form, 'title': 'Create Discount Rule',
    })


@login_required
def discount_rule_edit_view(request, pk):
    obj = get_object_or_404(DiscountRule, pk=pk)
    if request.method == 'POST':
        form = DiscountRuleForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, f'Discount Rule "{obj.name}" updated.')
            return redirect('discount_rule_list')
    else:
        form = DiscountRuleForm(instance=obj)
    return render(request, 'pricing/discount_rule_form.html', {
        'form': form, 'title': f'Edit Discount Rule: {obj.name}',
    })


@login_required
def discount_rule_delete_view(request, pk):
    obj = get_object_or_404(DiscountRule, pk=pk)
    if request.method == 'POST':
        obj.soft_delete()
        messages.success(request, f'Discount Rule "{obj.name}" deleted.')
        return redirect('discount_rule_list')
    return render(request, 'pricing/discount_rule_delete.html', {'object': obj})


# ── Customer Price Catalog API ─────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def customer_catalog_api(request, customer_pk):
    """
    Return all active CustomerPriceCatalogItems for a customer, keyed by
    item_id + unit_id so the SO form can look up overridden prices.
    Response:
      { customer_id, has_catalog, items: [{item_id, unit_id, price, item_code, item_name, unit_abbr}] }
    """
    from partners.models import Customer
    customer = get_object_or_404(Customer, pk=customer_pk)
    order_date = request.query_params.get('order_date')
    if order_date:
        try:
            effective_date = timezone.datetime.strptime(order_date, '%Y-%m-%d').date()
        except ValueError:
            return Response({'error': 'Invalid order_date. Use YYYY-MM-DD.'}, status=400)
    else:
        effective_date = timezone.now().date()
    catalogs = (
        CustomerPriceCatalog.objects
        .filter(
            customer=customer,
            is_active=True,
        )
        .filter(
            Q(start_date__isnull=True) | Q(start_date__lte=effective_date),
            Q(end_date__isnull=True) | Q(end_date__gte=effective_date),
        )
        .prefetch_related('items__item', 'items__unit')
        .order_by('start_date', 'name')
    )
    items = []
    seen = set()
    for cat in catalogs:
        for ci in cat.items.select_related('item', 'unit').all():
            key = (ci.item_id, ci.unit_id)
            if key in seen:
                continue
            seen.add(key)
            items.append({
                'item_id': ci.item_id,
                'unit_id': ci.unit_id,
                'price': str(ci.price),
                'item_code': ci.item.code,
                'item_name': ci.item.name,
                'unit_abbr': ci.unit.abbreviation,
                'catalog_name': cat.name,
            })
    return Response({
        'customer_id': customer.pk,
        'customer_name': customer.name,
        'effective_date': effective_date.isoformat(),
        'has_catalog': len(items) > 0,
        'items': items,
    })


# ── Customer Price Catalog Template Views ─────────────────────────────────

@login_required
def customer_catalog_list_view(request):
    catalogs = (
        CustomerPriceCatalog.objects
        .select_related('customer')
        .prefetch_related('items')
        .filter(is_active=True)
        .order_by('customer__name', 'name')
    )
    return render(request, 'pricing/customer_catalog_list.html', {'catalogs': catalogs})


@login_required
def customer_catalog_create_view(request):
    if request.method == 'POST':
        form = CustomerPriceCatalogForm(request.POST)
        formset = CustomerPriceCatalogItemFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            obj = form.save()
            formset = CustomerPriceCatalogItemFormSet(request.POST, instance=obj)
            if formset.is_valid():
                formset.save()
                messages.success(request, f'Customer Catalog "{obj.name}" created.')
                return redirect('customer_catalog_list')
    else:
        form = CustomerPriceCatalogForm()
        formset = CustomerPriceCatalogItemFormSet()
    return render(request, 'pricing/customer_catalog_form.html', {
        'form': form, 'formset': formset, 'title': 'Create Customer Price Catalog',
    })


@login_required
def customer_catalog_edit_view(request, pk):
    obj = get_object_or_404(CustomerPriceCatalog, pk=pk)
    if request.method == 'POST':
        form = CustomerPriceCatalogForm(request.POST, instance=obj)
        formset = CustomerPriceCatalogItemFormSet(request.POST, instance=obj)
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            messages.success(request, f'Customer Catalog "{obj.name}" updated.')
            return redirect('customer_catalog_list')
    else:
        form = CustomerPriceCatalogForm(instance=obj)
        formset = CustomerPriceCatalogItemFormSet(instance=obj)
    return render(request, 'pricing/customer_catalog_form.html', {
        'form': form, 'formset': formset, 'title': f'Edit: {obj.name}',
        'object': obj,
    })


@login_required
def customer_catalog_delete_view(request, pk):
    obj = get_object_or_404(CustomerPriceCatalog, pk=pk)
    if request.method == 'POST':
        obj.soft_delete()
        messages.success(request, f'Customer Catalog "{obj.name}" deleted.')
        return redirect('customer_catalog_list')
    return render(request, 'pricing/customer_catalog_delete.html', {'object': obj})
