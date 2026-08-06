"""
Supplier Catalog sync logic.

Shared between the admin UI (procurement.views.supplier_catalog_sync_view)
and the full inventory resync (inventory.management.commands.resync_inventory,
Phase 1c) so both apply the exact same pricing rules — a Purchase Order does
not silently drift out of sync with what the last full resync recorded.
"""
from django.utils import timezone

from procurement.models import (
    PurchaseOrderLine, GoodsReceiptLine, SupplierCatalogEntry, SupplierCatalogSyncState,
)


def gather_supplier_catalog_candidates(item_ids=None):
    """
    Build a unified list of Supplier Catalog price candidates from two sources:

      - POSTED/APPROVED Purchase Order lines — the agreed/ordered price,
        dated by the PO's order_date.
      - POSTED Goods Receipt lines linked to a PO — the price actually paid
        on receipt, borrowed from the matching PO line (same item+unit) or,
        if no exact-unit PO line exists, from any priced PO line for that
        item (using that line's unit instead), dated by the GRN's
        receipt_date.

    Candidates are returned unsorted; use prioritize_candidates() to order
    them for "GRN is the source of truth" application.
    """
    candidates = []

    po_lines = (
        PurchaseOrderLine.objects
        .filter(purchase_order__status__in=['POSTED', 'APPROVED'])
        .select_related('purchase_order__supplier', 'item', 'unit')
    )
    if item_ids is not None:
        po_lines = po_lines.filter(item_id__in=item_ids)

    for line in po_lines:
        if not line.unit_price or line.unit_price <= 0:
            continue
        po = line.purchase_order
        candidates.append({
            'supplier': po.supplier,
            'item': line.item,
            'unit': line.unit,
            'price': line.unit_price,
            'currency': po.currency or 'PHP',
            'date': po.order_date,
            'doc_number': po.document_number,
            'source': 'PO',
        })

    grn_lines = (
        GoodsReceiptLine.objects
        .filter(
            goods_receipt__status='POSTED',
            goods_receipt__purchase_order__isnull=False,
        )
        .select_related(
            'goods_receipt__supplier', 'goods_receipt__purchase_order',
            'item', 'unit',
        )
    )
    if item_ids is not None:
        grn_lines = grn_lines.filter(item_id__in=item_ids)

    for grn_line in grn_lines:
        grn = grn_line.goods_receipt
        po_line = (
            PurchaseOrderLine.objects
            .filter(
                purchase_order=grn.purchase_order,
                item=grn_line.item,
                unit=grn_line.unit,
            )
            .first()
        )

        if po_line and po_line.unit_price and po_line.unit_price > 0:
            entry_unit = grn_line.unit
            entry_price = po_line.unit_price
        else:
            fallback_po = (
                PurchaseOrderLine.objects
                .filter(purchase_order=grn.purchase_order, item=grn_line.item)
                .exclude(unit_price__isnull=True)
                .exclude(unit_price__lte=0)
                .first()
            )
            if not fallback_po:
                continue
            entry_unit = fallback_po.unit
            entry_price = fallback_po.unit_price

        candidates.append({
            'supplier': grn.supplier,
            'item': grn_line.item,
            'unit': entry_unit,
            'price': entry_price,
            'currency': grn.purchase_order.currency or 'PHP',
            'date': grn.receipt_date,
            'doc_number': grn.document_number,
            'source': 'GRN',
        })

    return candidates


def prioritize_candidates(candidates):
    """
    Order candidates so that applying them in sequence (each one overwriting
    any prior same-key entry) makes GRN data the source of truth: all PO
    candidates are applied first — latest PO wins among POs, giving items
    that haven't been received yet a sensible quoted/ordered price — then
    all GRN candidates are applied on top of that. Within GRNs, the latest
    receipt wins; and because GRNs are always applied last, a posted GRN,
    whenever one exists, overrides whatever PO price was set for that
    supplier+item+unit — regardless of which one is dated more recently.
    """
    po = sorted((c for c in candidates if c['source'] == 'PO'), key=lambda c: c['date'])
    grn = sorted((c for c in candidates if c['source'] == 'GRN'), key=lambda c: c['date'])
    return po + grn


def sync_supplier_catalog(item_ids=None):
    """
    Apply gather_supplier_catalog_candidates()/prioritize_candidates() to
    SupplierCatalogEntry: upsert every candidate, with GRN data overriding
    PO data for the same supplier+item+unit whenever a posted GRN exists.
    Item cost prices are never touched — only SupplierCatalogEntry rows.

    Returns a dict:
        created_count      – new SupplierCatalogEntry rows created
        updated_count      – existing rows upserted (may be a no-op price)
        touched_item_count – distinct items touched
        changes            – list of dicts (item, supplier, unit, old_price,
                              new_price, is_new, source) for rows whose price
                              actually changed — for reporting to a human.
    """
    entries_qs = SupplierCatalogEntry.objects.all()
    if item_ids is not None:
        entries_qs = entries_qs.filter(item_id__in=item_ids)
    before_map = {
        (e.supplier_id, e.item_id, e.unit_id): e.unit_price
        for e in entries_qs
    }

    candidates = prioritize_candidates(gather_supplier_catalog_candidates(item_ids=item_ids))

    created_count = 0
    updated_count = 0
    touched_keys = set()
    key_source = {}

    for c in candidates:
        entry, created = SupplierCatalogEntry.objects.update_or_create(
            supplier=c['supplier'],
            item=c['item'],
            unit=c['unit'],
            defaults={
                'unit_price': c['price'],
                'currency': c['currency'],
                'last_po_date': c['date'],
                'last_po_number': c['doc_number'],
            },
        )
        if created:
            created_count += 1
        else:
            updated_count += 1
        key = (c['supplier'].pk, c['item'].pk, c['unit'].pk)
        touched_keys.add(key)
        key_source[key] = c['source']  # last write wins, matching the entry's final state

    changes = []
    if touched_keys:
        touched_item_ids = {key[1] for key in touched_keys}
        final_entries = (
            SupplierCatalogEntry.objects
            .filter(item_id__in=touched_item_ids)
            .select_related('item', 'supplier', 'unit')
        )
        for e in final_entries:
            key = (e.supplier_id, e.item_id, e.unit_id)
            if key not in touched_keys:
                continue
            old_price = before_map.get(key)
            if old_price is not None and old_price == e.unit_price:
                continue
            changes.append({
                'item': e.item,
                'supplier': e.supplier,
                'unit': e.unit,
                'old_price': old_price,
                'new_price': e.unit_price,
                'is_new': old_price is None,
                'source': key_source.get(key, 'PO'),
            })

    changes.sort(key=lambda c: (c['item'].code, c['supplier'].name))

    # Clear the "resync happened, please review" flag — the user just did.
    state = SupplierCatalogSyncState.get_instance()
    state.last_catalog_sync_at = timezone.now()
    state.save(update_fields=['last_catalog_sync_at'])

    return {
        'created_count': created_count,
        'updated_count': updated_count,
        'touched_item_count': len({key[1] for key in touched_keys}),
        'changes': changes,
    }
