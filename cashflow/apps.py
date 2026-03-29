from django.apps import AppConfig


class CashflowConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'cashflow'
    verbose_name = 'Cash Flow Management'

    def ready(self):
        import cashflow.signals  # noqa: F401 — registers all signal handlers
