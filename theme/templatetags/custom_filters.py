from django import template
from decimal import Decimal

register = template.Library()


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
