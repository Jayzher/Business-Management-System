from django import template
from decimal import Decimal
from django.utils.html import escape
from django.utils.safestring import mark_safe

register = template.Library()


_SORT_ICON_SVG = (
    '<svg class="wis-sort-icon {state}" width="9" height="11" viewBox="0 0 10 12" '
    'aria-hidden="true" focusable="false">'
    '<path class="wis-sort-up" d="M5 0 9.33 5H0.67L5 0Z"></path>'
    '<path class="wis-sort-down" d="M5 12 0.67 7H9.33L5 12Z"></path>'
    '</svg>'
)


@register.simple_tag(takes_context=True)
def sort_link(context, field, label, current_sort='', current_dir='desc'):
    """
    Render a sortable column header link that preserves all other query
    params (filters, etc.) and resets pagination to page 1 on re-sort.
    Usage: {% sort_link 'date' 'Date' sort dir %}

    Renders an inline SVG caret rather than a Font Awesome glyph so the sort
    indicator always renders crisply regardless of icon-font load state.
    """
    request = context['request']
    params = request.GET.copy()
    is_active = current_sort == field
    if is_active:
        next_dir = 'asc' if current_dir == 'desc' else 'desc'
        state = 'asc' if current_dir == 'asc' else 'desc'
    else:
        next_dir = 'desc'
        state = ''
    params['sort'] = field
    params['dir'] = next_dir
    params.pop('page', None)
    url = f'?{params.urlencode()}'
    icon = _SORT_ICON_SVG.format(state=state)
    return mark_safe(
        f'<a href="{escape(url)}" class="wis-sort-link{" active" if is_active else ""}">'
        f'<span>{escape(label)}</span>{icon}</a>'
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
