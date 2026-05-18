"""
sync/save_guard.py — Guard against duplicate-key errors caused by stale local_cache.

THE PROBLEM:
  1. Device A creates a record → INSERT succeeds on Neon.
  2. The on_commit mirror to local_cache fails (network hiccup, timeout, crash).
  3. Device A's local_cache doesn't have the row.
  4. Next request: router reads from local_cache → row not found → app thinks
     it doesn't exist → tries INSERT on Neon → IntegrityError (duplicate key).

  This also happens when:
  - The server restarts before the mirror callback fires.
  - The changelog sync hasn't caught up yet (still in progress).
  - A WebSocket data_changed event was missed.

THE FIX:
  A pre_save signal that detects when Django is about to INSERT a row that
  already exists on Neon.  When detected, it:
  1. Forces the instance into "update" mode (instance._state.adding = False)
  2. Immediately mirrors the existing Neon row to local_cache (fixes the stale cache)

  This is a SAFETY NET — it should rarely fire in normal operation.  When it
  does fire, it means the local_cache was stale and we're preventing a crash.

ALSO:
  A post_save error handler that catches IntegrityError on INSERT and retries
  as an UPDATE.  This is the fallback for cases where the pre_save check
  didn't catch it (race conditions, concurrent requests).
"""

import logging
import threading

from django.conf import settings
from django.db import IntegrityError
from django.db.models.signals import pre_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)

# Thread-local to prevent re-entrancy
_GUARD_ACTIVE = threading.local()


def _is_neon_primary() -> bool:
    return getattr(settings, 'SYNC_MODE', 'offline') == 'neon_primary'


@receiver(pre_save)
def guard_duplicate_insert(sender, instance, using, **kwargs):
    """
    Pre-save guard: if Django is about to INSERT (instance._state.adding=True)
    to Neon, check if the row already exists there.  If it does, switch to
    UPDATE mode to prevent IntegrityError.

    This fires ONLY when:
      - We're in neon_primary mode
      - The write is going to 'default' (Neon)
      - The instance is marked as "adding" (INSERT)

    Two checks:
      1. If PK is set: check if that PK exists on Neon.
      2. If PK is None (auto-gen): check unique business fields
         (document_number, sale_no, etc.) to detect re-submissions.

    Performance: This adds one SELECT query per INSERT to Neon.
    The check is fast (indexed unique fields) and prevents crashes.
    """
    from sync.signals import SYNCED_APP_LABELS

    if sender._meta.app_label not in SYNCED_APP_LABELS:
        return
    if not _is_neon_primary():
        return
    if using != 'default':
        return
    if getattr(_GUARD_ACTIVE, 'value', False):
        return

    # Only check when Django thinks this is a new row (INSERT)
    if not instance._state.adding:
        return

    _GUARD_ACTIVE.value = True
    try:
        existing = None

        if instance.pk is not None:
            # Check if this PK already exists on Neon
            existing = sender._default_manager.using('default').filter(
                pk=instance.pk
            ).first()
        else:
            # PK is None (auto-generated) — only check unique business fields
            # if the model actually has any (skip for models with no unique fields).
            if _has_unique_business_fields(sender):
                existing = _find_by_unique_fields(sender, instance)

        if existing is not None:
            # Row already exists on Neon — switch to UPDATE mode
            instance.pk = existing.pk
            instance._state.adding = False
            instance._state.db = 'default'

            logger.info(
                'SAVE GUARD: %s pk=%s already exists on Neon. '
                'Switching from INSERT to UPDATE (local_cache was stale).',
                sender.__name__, existing.pk,
            )

            # Also fix local_cache immediately so future reads are correct
            _repair_local_cache(sender, existing.pk)

    except Exception as exc:
        # If the check itself fails, let the save proceed normally.
        # Worst case: it'll get an IntegrityError which safe_save can handle.
        logger.debug('Save guard check failed for %s pk=%s: %s',
                     sender.__name__, instance.pk, exc)
    finally:
        _GUARD_ACTIVE.value = False


# ── Cache for _has_unique_business_fields (computed once per model) ─────
_unique_fields_cache = {}


def _has_unique_business_fields(sender) -> bool:
    """
    Check if a model has any unique fields besides the PK.
    Cached per model class to avoid repeated introspection.
    """
    key = sender._meta.label
    if key in _unique_fields_cache:
        return _unique_fields_cache[key]

    has_unique = False

    # Check unique_together
    if sender._meta.unique_together:
        has_unique = True

    # Check UniqueConstraint
    if not has_unique:
        for constraint in getattr(sender._meta, 'constraints', []):
            if hasattr(constraint, 'fields'):
                has_unique = True
                break

    # Check field-level unique=True
    if not has_unique:
        for field in sender._meta.concrete_fields:
            if field.unique and not field.primary_key:
                has_unique = True
                break

    _unique_fields_cache[key] = has_unique
    return has_unique


def _repair_local_cache(sender, pk):
    """
    Immediately copy the existing Neon row to local_cache.
    This fixes the stale cache that caused the duplicate-insert attempt.
    """
    try:
        obj = sender._default_manager.using('default').filter(pk=pk).first()
        if obj is None:
            return

        concrete_fields = [
            f for f in sender._meta.concrete_fields if not f.primary_key
        ]
        update_fields = [f.attname for f in concrete_fields]

        # Temporarily disable auto_now/auto_now_add
        auto_fields = []
        for field in sender._meta.get_fields():
            if hasattr(field, 'auto_now') and field.auto_now:
                field.auto_now = False
                auto_fields.append(('auto_now', field))
            if hasattr(field, 'auto_now_add') and field.auto_now_add:
                field.auto_now_add = False
                auto_fields.append(('auto_now_add', field))

        try:
            obj._state.adding = True
            obj._state.db = 'local_cache'

            if update_fields:
                sender._default_manager.using('local_cache').bulk_create(
                    [obj],
                    update_conflicts=True,
                    update_fields=update_fields,
                    unique_fields=['id'],
                )
            else:
                sender._default_manager.using('local_cache').bulk_create(
                    [obj], ignore_conflicts=True,
                )
        finally:
            for attr, field in auto_fields:
                setattr(field, attr, True)

        logger.debug('Repaired local_cache for %s pk=%s', sender.__name__, pk)

    except Exception as exc:
        logger.debug('Failed to repair local_cache for %s pk=%s: %s',
                     sender.__name__, pk, exc)


def safe_save(instance, **kwargs):
    """
    Drop-in replacement for instance.save() that handles IntegrityError
    by retrying as an UPDATE.

    Usage:
        from sync.save_guard import safe_save
        safe_save(my_obj)  # instead of my_obj.save()

    Or for specific fields:
        safe_save(my_obj, update_fields=['status', 'total'])

    This is useful in views/services where you're not sure if the row
    already exists on Neon (e.g., after a failed previous attempt).
    """
    try:
        instance.save(**kwargs)
    except IntegrityError as exc:
        error_msg = str(exc).lower()
        # Only retry for duplicate key / unique constraint violations
        if 'duplicate' in error_msg or 'unique' in error_msg or 'already exists' in error_msg:
            logger.info(
                'safe_save: IntegrityError on %s pk=%s, retrying as UPDATE. Error: %s',
                type(instance).__name__, instance.pk, exc,
            )

            # Try to find the existing row by PK or unique fields
            sender = type(instance)
            existing = None

            if instance.pk is not None:
                existing = sender._default_manager.using('default').filter(
                    pk=instance.pk
                ).first()

            if existing is None:
                # PK didn't match — try unique fields (document_number, sale_no, etc.)
                existing = _find_by_unique_fields(sender, instance)

            if existing is not None:
                # Update the existing row with the new data
                instance.pk = existing.pk
                instance._state.adding = False
                instance._state.db = 'default'
                instance.save(**kwargs)

                # Repair local_cache
                _repair_local_cache(sender, instance.pk)
            else:
                # Can't find the conflicting row — re-raise
                raise
        else:
            # Not a duplicate key error — re-raise
            raise


def safe_create(model, **field_values):
    """
    Create a model instance, handling the case where it already exists on Neon.

    Returns the instance (created or updated).

    Usage:
        from sync.save_guard import safe_create
        sale = safe_create(POSSale, sale_no='POS-001', register=reg, ...)
    """
    instance = model(**field_values)
    safe_save(instance)
    return instance


def _find_by_unique_fields(sender, instance):
    """
    Try to find an existing row on Neon that matches the instance's
    unique constraint fields (excluding PK).

    Checks:
      1. Model-level unique_together / UniqueConstraint
      2. Field-level unique=True fields (e.g., document_number, sale_no)
    """
    # Collect unique field sets
    unique_lookups = []

    # unique_together (legacy)
    for fields in sender._meta.unique_together:
        lookup = {}
        for field_name in fields:
            val = getattr(instance, field_name, None)
            if val is not None:
                lookup[field_name] = val
        if lookup and len(lookup) == len(fields):
            unique_lookups.append(lookup)

    # UniqueConstraint (modern)
    for constraint in getattr(sender._meta, 'constraints', []):
        if hasattr(constraint, 'fields'):
            condition = getattr(constraint, 'condition', None)
            # Only use unconditional unique constraints
            if condition is None:
                lookup = {}
                for field_name in constraint.fields:
                    val = getattr(instance, field_name, None)
                    if val is not None:
                        lookup[field_name] = val
                if lookup and len(lookup) == len(constraint.fields):
                    unique_lookups.append(lookup)

    # Field-level unique=True (e.g., document_number, sale_no, invoice_number)
    for field in sender._meta.concrete_fields:
        if field.unique and not field.primary_key:
            val = field.value_from_object(instance)
            if val is not None and val != '':
                unique_lookups.append({field.attname: val})

    # Try each unique lookup
    for lookup in unique_lookups:
        try:
            existing = sender._default_manager.using('default').filter(**lookup).first()
            if existing is not None:
                return existing
        except Exception:
            continue

    return None
