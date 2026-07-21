from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import router, transaction

from services.models import CustomerService
from core.models import Invoice

# The alias these models' writes actually land on (see
# inventory_system/db_router.py — 'local_cache' in neon_primary mode,
# 'default' in offline mode). A bare transaction.atomic() defaults to
# 'default', the wrong connection whenever SYNC_MODE=neon_primary — see the
# identical note in sales/signals.py, whose _WRITE_DB this mirrors.
_WRITE_DB = router.db_for_write(Invoice) or 'default'

# Fields whose save must NOT trigger an invoice resync. service_complete()
# (services/views.py) already syncs the invoice synchronously before making
# this status-only save — re-syncing again here is at best redundant and,
# without a real transaction on the alias these models actually write to
# (the bug just fixed above), was a second unguarded delete+recreate able to
# interleave with the first. Genuine content edits (product lines, quotation,
# discount, etc.) go through the form and save the whole object
# (update_fields=None), so they still resync normally.
_STATUS_ONLY_SERVICE_FIELDS = frozenset({
    'status', 'invoice', 'posted_by', 'posted_at', 'completion_date', 'updated_at',
})


@receiver(post_save, sender=CustomerService)
def sync_service_changes_to_invoice(sender, instance, created, **kwargs):
    """
    When a Service is updated, synchronize changes to its linked invoice (if any).
    Uses on_commit to ensure formsets are saved.
    """
    if created or not instance.invoice_id:
        return

    update_fields = kwargs.get('update_fields')
    if update_fields is not None and set(update_fields) <= _STATUS_ONLY_SERVICE_FIELDS:
        return

    def do_sync():
        with transaction.atomic(using=_WRITE_DB):
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
