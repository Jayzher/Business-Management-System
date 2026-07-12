"""
sync/middleware.py — Pause the background sync worker during Django Admin
deletes.

THE PROBLEM (same root cause already fixed once for resync_inventory, see
inventory/management/commands/resync_inventory.py and
docs_archive/DATABASE_LOCK_FIX.md):

  Deleting an object in Django Admin (single "Delete" or the "Delete
  selected" bulk action) runs the ENTIRE cascade — the object plus every
  related row Django collects via on_delete=CASCADE — inside one
  transaction on 'local_cache'. For objects with non-trivial related data
  this transaction can run long enough that the background sync worker
  thread (sync/background_sync.py), which also writes to 'local_cache' on
  its own schedule, ends up fighting the admin request for SQLite's single
  writer lock. Once that contention outlasts busy_timeout, the request
  fails with "database is locked".

THE FIX:
  Pause the background worker for the duration of any admin delete request
  and always resume it afterward — the exact mechanism
  sync/background_sync.pause_worker()/resume_worker() was built for.
"""
import logging

logger = logging.getLogger(__name__)


class PauseSyncForAdminDeleteMiddleware:
    """Pause the background sync worker for the duration of a Django Admin
    delete request (single-object confirm POST or bulk "Delete selected").
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not self._is_admin_delete(request):
            return self.get_response(request)

        from sync.background_sync import pause_worker, resume_worker
        pause_worker()
        try:
            return self.get_response(request)
        finally:
            resume_worker()

    @staticmethod
    def _is_admin_delete(request) -> bool:
        if request.method != 'POST':
            return False
        if not request.path.startswith('/admin/'):
            return False
        # Single-object delete confirmation: /admin/<app>/<model>/<pk>/delete/
        if request.path.rstrip('/').endswith('/delete'):
            return True
        # "Delete selected" bulk action posted from the changelist
        if request.POST.get('action') == 'delete_selected':
            return True
        return False
