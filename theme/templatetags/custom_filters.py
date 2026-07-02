from django import template
from decimal import Decimal
from django.utils.html import escape
from django.utils.safestring import mark_safe

register = template.Library()


@register.simple_tag(takes_context=True)
def sort_link(context, field, label, current_sort='', current_dir='desc'):
    """
    Render a sortable column header link that preserves all other query
    params (filters, etc.) and resets pagination to page 1 on re-sort.
    Usage: {% sort_link 'date' 'Date' sort dir %}
    """
    request = context['request']
    params = request.GET.copy()
    if current_sort == field:
        next_dir = 'asc' if current_dir == 'desc' else 'desc'
        icon = 'fa-sort-up' if current_dir == 'asc' else 'fa-sort-down'
    else:
        next_dir = 'desc'
        icon = 'fa-sort text-muted'
    params['sort'] = field
    params['dir'] = next_dir
    params.pop('page', None)
    url = f'?{params.urlencode()}'
    return mark_safe(
        f'<a href="{escape(url)}" class="text-dark text-decoration-none">'
        f'{escape(label)} <i class="fas {icon} small"></i></a>'
    )


@register.filter(name='decimal2')
def decimal2(value):
    """Format a number to 2 decimal places."""
    if value is None or value == '':
        return '0.00'
    try:
        return f"{float(value):.2f}"
    except (ValueError, TypeError):
        return value


@register.filter(name='currency')
def currency(value):
    """Format a number as currency with 2 decimal places and thousand separators."""
    if value is None or value == '':
        return '0.00'
    try:
        return f"{float(value):,.2f}"
    except (ValueError, TypeError):
        return value


@register.filter(name='get_item')
def get_item(dictionary, key):
    """Look up a key in a dict: {{ my_dict|get_item:key }}."""
    if not isinstance(dictionary, dict):
        return None
    return dictionary.get(key)


@register.filter(name='subtract')
def subtract(value, arg):
    """Subtract arg from value: {{ a|subtract:b }}."""
    try:
        return Decimal(str(value)) - Decimal(str(arg))
    except Exception:
        return value


@register.filter(name='abs_value')
def abs_value(value):
    """Return absolute value: {{ value|abs_value }}."""
    try:
        return abs(Decimal(str(value)))
    except Exception:
        return value
