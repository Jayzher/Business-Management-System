from decimal import Decimal
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction

from services.models import CustomerService
from core.models import Invoice, InvoiceLine


@receiver(post_save, sender=CustomerService)
def sync_service_changes_to_invoice(sender, instance, created, **kwargs):
    """
    When a Service is updated, synchronize changes to its linked invoice (if any).
    Uses on_commit to ensure formsets are saved.
    """
    if created or not instance.invoice_id:
        return

    def do_sync():
        with transaction.atomic():
            # Find the non-void invoice linked to this service
            invoice = Invoice.objects.select_for_update().filter(
                pk=instance.invoice_id,
                is_void=False
            ).first()
            
            if not invoice:
                return
                
            # Use the same recreative logic as in service_complete
            _sync_invoice_from_service(invoice, instance)

    transaction.on_commit(do_sync)


def _sync_invoice_from_service(invoice, svc):
    """
    Helper to sync invoice header and lines from a service.
    """
    from audit.models import AuditLog
    import logging
    logger = logging.getLogger(__name__)

    # Recompute amounts
    if svc.quotation_amount > 0:
        val = svc.discount_value or Decimal('0')
        if svc.discount_type == 'PERCENT':
            discount_amt = (svc.quotation_amount * val / Decimal('100')).quantize(Decimal('0.01'))
        else:
            discount_amt = val
        subtotal = svc.quotation_amount
        grand_total = max(subtotal - discount_amt, Decimal('0'))
    else:
        subtotal = svc.product_lines_total + svc.other_materials_total + svc.bundles_total
        discount_amt = svc.discount_amount
        grand_total = max(subtotal - discount_amt, Decimal('0'))

    partial_paid = svc.partial_payment_amount_value
    if partial_paid > grand_total:
        partial_paid = grand_total
    
    remaining_balance = max(grand_total - partial_paid, Decimal('0'))
    
    if partial_paid > 0:
        invoice_subtotal = remaining_balance
        invoice_discount = Decimal('0')
        invoice_grand_total = remaining_balance
        invoice_notes = f'Service: {svc.service_name} (Remaining balance after ₱{partial_paid:,.2f} partial payment)'
    else:
        invoice_subtotal = subtotal
        invoice_discount = discount_amt
        invoice_grand_total = grand_total
        invoice_notes = f'Service: {svc.service_name}'

    # Update invoice header
    invoice.subtotal = invoice_subtotal
    invoice.discount_total = invoice_discount
    invoice.grand_total = invoice_grand_total
    invoice.notes = invoice_notes
    invoice.customer_name = svc.customer_name
    invoice.customer_address = svc.address
    invoice.save(update_fields=[
        'subtotal', 'discount_total', 'grand_total', 'notes',
        'customer_name', 'customer_address', 'updated_at'
    ])
    
    # Recreate lines
    invoice.lines.all().delete()

    new_lines = []
    if svc.quotation_amount > 0:
        line_description = svc.service_name or 'Service'
        if partial_paid > 0:
            line_description += f' (Balance after ₱{partial_paid:,.2f} partial payment)'

        new_lines.append(InvoiceLine(
            invoice=invoice,
            item_code='SVC-QUOT',
            item_name=line_description,
            qty=Decimal('1'),
            unit='svc',
            unit_price=invoice_grand_total,
            line_total=invoice_grand_total,
        ))
    else:
        svc_lines = list(svc.lines.select_related('item', 'unit').all())
        svc_materials = list(svc.other_materials.all())

        for line in svc_lines:
            new_lines.append(InvoiceLine(
                invoice=invoice,
                item_code=line.item.code,
                item_name=line.item.name,
                qty=line.qty,
                unit=line.unit.abbreviation,
                unit_price=line.unit_price,
                line_total=line.line_total,
            ))

        for mat in svc_materials:
            new_lines.append(InvoiceLine(
                invoice=invoice,
                item_code='MAT',
                item_name=mat.item_name,
                qty=mat.qty,
                unit='unit',
                unit_price=mat.unit_price,
                line_total=mat.line_total,
            ))

        if not svc_lines and not svc_materials:
            new_lines.append(InvoiceLine(
                invoice=invoice,
                item_code='SVC',
                item_name=svc.service_name,
                qty=Decimal('1'),
                unit='svc',
                unit_price=grand_total,
                line_total=grand_total,
            ))

    if new_lines:
        InvoiceLine.objects.bulk_create(new_lines)

    # Log the sync
    AuditLog.objects.create(
        action='UPDATE',
        model_name='Invoice',
        object_id=invoice.id,
        object_repr=str(invoice),
        changes={'source': f'Synced from Service {svc.service_number} update'},
        user=getattr(svc, 'updated_by', invoice.created_by),
    )
