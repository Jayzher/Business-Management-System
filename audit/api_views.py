from rest_framework import viewsets, mixins, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import OrderingFilter

from audit.models import AuditLog, ManualLog
from audit.serializers import AuditLogSerializer, ManualLogSerializer, ManualLogCreateSerializer
from audit.filters import AuditLogFilter, ManualLogFilter


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint for system-generated audit logs.
    Read-only — logs are created by the system, not by users.

    Supports:
      - Pagination: ?page=1&page_size=30
      - Filtering: ?action=POST&model_name=DeliveryNote&user=1
      - Search: ?q=DN-000148
      - Date range: ?date_from=2026-04-01&date_to=2026-04-30
      - Ordering: ?ordering=-timestamp (default)
    """
    queryset = AuditLog.objects.select_related('user').all()
    serializer_class = AuditLogSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_class = AuditLogFilter
    ordering_fields = ['timestamp', 'action', 'model_name']
    ordering = ['-timestamp']

    @action(detail=False, methods=['get'])
    def filter_options(self, request):
        """Return distinct values for filter dropdowns."""
        return Response({
            'actions': list(
                AuditLog.objects.values_list('action', flat=True)
                .distinct().order_by('action')
            ),
            'models': list(
                AuditLog.objects.values_list('model_name', flat=True)
                .distinct().order_by('model_name')
            ),
            'users': list(
                AuditLog.objects.filter(user__isnull=False)
                .values_list('user__id', 'user__username')
                .distinct().order_by('user__username')
            ),
        })


class ManualLogViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    """
    API endpoint for manual change logs.
    Supports list, retrieve, and create (no update/delete — logs are immutable).

    Supports:
      - Pagination: ?page=1&page_size=30
      - Filtering: ?action=FIX&table_name=catalog_item
      - Search: ?q=cost_price
      - Date range: ?date_from=2026-04-01&date_to=2026-04-30
      - Ordering: ?ordering=-created_at (default)
    """
    queryset = ManualLog.objects.select_related('user').all()
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_class = ManualLogFilter
    ordering_fields = ['created_at', 'action', 'table_name']
    ordering = ['-created_at']

    def get_serializer_class(self):
        if self.action == 'create':
            return ManualLogCreateSerializer
        return ManualLogSerializer

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=False, methods=['get'])
    def filter_options(self, request):
        """Return distinct values for filter dropdowns."""
        return Response({
            'actions': ManualLog.ACTION_CHOICES,
            'tables': list(
                ManualLog.objects.values_list('table_name', flat=True)
                .distinct().order_by('table_name')
            ),
        })
