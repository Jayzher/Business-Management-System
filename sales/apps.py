from django.apps import AppConfig


class SalesConfig(AppConfig):
    name = 'sales'
    
    def ready(self):
        """Import signals when the app is ready."""
        import sales.signals  # noqa
