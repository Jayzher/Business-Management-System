import django_filters
from django.db.models import Q
from audit.models import AuditLog, ManualLog


class AuditLogFilter(django_filters.FilterSet):
    action = django_filters.CharFilter(lookup_expr='exact')
    model_name = django_filters.CharFilter(lookup_expr='exact')
    user = django_filters.NumberFilter(field_name='user_id')
    q = django_filters.CharFilter(method='search_all')
    date_from = django_filters.DateFilter(field_name='timestamp', lookup_expr='date__gte')
    date_to = django_filters.DateFilter(field_name='timestamp', lookup_expr='date__lte')

    class Meta:
        model = AuditLog
        fields = ['action', 'model_name', 'user', 'q', 'date_from', 'date_to']

    def search_all(self, queryset, name, value):
        return queryset.filter(
            Q(object_repr__icontains=value) | Q(model_name__icontains=value)
        )


class ManualLogFilter(django_filters.FilterSet):
    action = django_filters.CharFilter(lookup_expr='exact')
    table_name = django_filters.CharFilter(lookup_expr='exact')
    q = django_filters.CharFilter(method='search_all')
    date_from = django_filters.DateFilter(field_name='created_at', lookup_expr='date__gte')
    date_to = django_filters.DateFilter(field_name='created_at', lookup_expr='date__lte')

    class Meta:
        model = ManualLog
        fields = ['action', 'table_name', 'q', 'date_from', 'date_to']

    def search_all(self, queryset, name, value):
        return queryset.filter(
            Q(reason__icontains=value) | Q(table_name__icontains=value) |
            Q(fields_changed__icontains=value) | Q(notes__icontains=value)
        )
