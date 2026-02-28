from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from pricing.models import PriceList, PriceListItem, DiscountRule
from pricing.serializers import PriceListSerializer, PriceListItemSerializer, DiscountRuleSerializer
from pricing.forms import PriceListForm, PriceListItemFormSet, DiscountRuleForm


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
