from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction

from services.models import CustomerService
from core.models import Invoice


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
    Sync invoice header and lines from a service, via the same
    sync_invoice_from_service() helper the completion write path
    (services/views.py::service_complete) uses — bills the full job value
    and leaves any partial payment already collected as its own
    InvoicePayment, never netted out of the total (see audit finding C2).
    An earlier version of this function had its own, separate copy of the
    pre-fix "remaining balance" logic that silently undid that fix on the
    next unrelated service edit.
    """
    from audit.models import AuditLog
    from services.automation import sync_invoice_from_service

    before_subtotal = invoice.subtotal
    before_grand_total = invoice.grand_total

    sync_invoice_from_service(invoice, svc)

    changes = []
    if invoice.subtotal != before_subtotal:
        changes.append(f"Subtotal: {before_subtotal} → {invoice.subtotal}")
    if invoice.grand_total != before_grand_total:
        changes.append(f"Grand total: {before_grand_total} → {invoice.grand_total}")

    # Log the sync
    AuditLog.objects.create(
        action='UPDATE',
        model_name='Invoice',
        object_id=invoice.id,
        object_repr=str(invoice),
        changes={
            'source': f'Synced from Service {svc.service_number} update',
            'updates': changes,
        },
        user=getattr(svc, 'updated_by', invoice.created_by),
    )
