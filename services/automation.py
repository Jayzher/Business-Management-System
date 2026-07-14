"""
Service invoice automation — shared between the completion write path
(services/views.py::service_complete) and the edit-after-completion signal
(services/signals.py), so the two can never compute the invoice
differently. An earlier version of the signal had its own, separate copy
of this logic that kept netting a partial payment out of the invoice
total instead of billing the full job value — silently undoing that fix
on the very next unrelated edit to the service.
"""
from decimal import Decimal


def compute_service_invoice_amounts(svc):
    """
    Return (subtotal, discount_amt, grand_total) — the FULL value the
    customer owes for this job, regardless of any partial payment already
    collected. Mirrors CustomerService's own pricing rules.
    """
    if svc.quotation_amount > 0:
        # Customer pays the quotation. Discount is applied to the quotation.
        val = svc.discount_value or Decimal('0')
        if svc.discount_type == 'PERCENT':
            discount_amt = (svc.quotation_amount * val / Decimal('100')).quantize(Decimal('0.01'))
        else:
            discount_amt = val
        subtotal = svc.quotation_amount
    else:
        # No quotation — charge whatever the individual lines total
        subtotal = svc.product_lines_total + svc.other_materials_total + svc.bundles_total
        discount_amt = svc.discount_amount

    grand_total = max(subtotal - discount_amt, Decimal('0'))
    return subtotal, discount_amt, grand_total


def sync_invoice_from_service(invoice, svc):
    """
    Recreate an invoice's header and lines from the current state of a
    CustomerService.

    Always bills the FULL job value — a partial payment already collected
    is recorded separately as its own InvoicePayment by the caller at the
    moment it's actually collected (service_complete), never netted out of
    the invoice total itself. Re-syncing later (e.g. after an unrelated
    edit to the service) must not re-record that payment — this function
    only touches the invoice header/lines, never InvoicePayment rows.

    Returns the number of InvoiceLine rows created.
    """
    from core.models import InvoiceLine

    subtotal, discount_amt, grand_total = compute_service_invoice_amounts(svc)

    partial_paid = svc.partial_payment_amount_value
    if partial_paid > grand_total:
        partial_paid = grand_total

    notes = f'Service: {svc.service_name}'
    if partial_paid > 0:
        notes += f' (₱{partial_paid:,.2f} collected in advance)'

    invoice.subtotal = subtotal
    invoice.discount_total = discount_amt
    invoice.grand_total = grand_total
    invoice.notes = notes
    invoice.customer_name = svc.customer_name
    invoice.customer_address = svc.address
    invoice.save(update_fields=[
        'subtotal', 'discount_total', 'grand_total', 'notes',
        'customer_name', 'customer_address', 'updated_at',
    ])

    invoice.lines.all().delete()
    count = 0

    if svc.quotation_amount > 0:
        # Quotation-based: a single service line. Material/part costs are
        # internal COGS and don't appear as customer-facing line items.
        InvoiceLine.objects.create(
            invoice=invoice,
            item_code='SVC-QUOT',
            item_name=svc.service_name or 'Service',
            qty=Decimal('1'),
            unit='svc',
            unit_price=grand_total,
            line_total=grand_total,
        )
        count = 1
    else:
        lines = list(svc.lines.select_related('item', 'unit').all())
        other_mats = list(svc.other_materials.all())

        for line in lines:
            InvoiceLine.objects.create(
                invoice=invoice,
                item_code=line.item.code,
                item_name=line.item.name,
                qty=line.qty,
                unit=line.unit.abbreviation,
                unit_price=line.unit_price,
                line_total=line.line_total,
            )
            count += 1

        for mat in other_mats:
            InvoiceLine.objects.create(
                invoice=invoice,
                item_code='MAT',
                item_name=mat.item_name,
                qty=mat.qty,
                unit='unit',
                unit_price=mat.unit_price,
                line_total=mat.line_total,
            )
            count += 1

        if not lines and not other_mats:
            InvoiceLine.objects.create(
                invoice=invoice,
                item_code='SVC',
                item_name=svc.service_name,
                qty=Decimal('1'),
                unit='svc',
                unit_price=grand_total,
                line_total=grand_total,
            )
            count = 1

    return count
