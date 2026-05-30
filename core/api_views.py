"""
DRF API Views for core app (Invoices, Expenses, etc.)
"""
from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend, FilterSet, CharFilter, DateFilter, BooleanFilter
from django.db.models import Q, Sum, DecimalField
from django.db.models.functions import Coalesce
from decimal import Decimal

from core.models import Invoice, Expense, ExpenseCategory, SalesChannel
from core.serializers import (
    InvoiceListSerializer, InvoiceDetailSerializer,
    ExpenseSerializer, ExpenseCategorySerializer,
    SalesChannelSerializer
)


class InvoiceFilter(FilterSet):
    """Custom filter for Invoice model."""
    
    # Date range filters
    date_from = DateFilter(field_name='date', lookup_expr='gte')
    date_to = DateFilter(field_name='date', lookup_expr='lte')
    
    # Payment status filters
    is_paid = BooleanFilter(field_name='is_paid')
    is_void = BooleanFilter(field_name='is_void')
    
    # Customer search
    customer = CharFilter(field_name='customer_name', lookup_expr='icontains')
    
    # Invoice number search
    invoice_number = CharFilter(field_name='invoice_number', lookup_expr='icontains')
    
    # Source filters
    has_sales_order = BooleanFilter(method='filter_has_sales_order')
    has_pos_sale = BooleanFilter(method='filter_has_pos_sale')
    
    def filter_has_sales_order(self, queryset, name, value):
        if value:
            return queryset.filter(sales_order__isnull=False)
        return queryset.filter(sales_order__isnull=True)
    
    def filter_has_pos_sale(self, queryset, name, value):
        if value:
            return queryset.filter(pos_sale__isnull=False)
        return queryset.filter(pos_sale__isnull=True)
    
    class Meta:
        model = Invoice
        fields = [
            'date_from', 'date_to', 'is_paid', 'is_void',
            'customer', 'invoice_number', 'has_sales_order', 'has_pos_sale'
        ]


class InvoiceViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API ViewSet for Invoices with pagination and filtering.
    
    Provides:
    - List view with pagination
    - Detail view with lines and payments
    - Filtering by date, customer, payment status, etc.
    - Search by invoice number or customer name
    - Ordering by date, amount, etc.
    
    Endpoints:
    - GET /api/invoices/ - List all invoices (paginated)
    - GET /api/invoices/{id}/ - Get invoice detail
    - GET /api/invoices/summary/ - Get invoice summary statistics
    - GET /api/invoices/unpaid/ - List unpaid invoices
    - GET /api/invoices/overdue/ - List overdue invoices
    """
    
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = InvoiceFilter
    search_fields = ['invoice_number', 'customer_name', 'customer_tin']
    ordering_fields = ['date', 'grand_total', 'created_at', 'invoice_number']
    ordering = ['-date', '-created_at']
    
    def get_queryset(self):
        """
        Get invoices excluding those linked to CustomerService.
        Optimizes queries with select_related and prefetch_related.
        """
        # Exclude service invoices (they're managed in services app)
        service_invoice_ids = Invoice.objects.filter(
            customer_services__isnull=False
        ).values_list('id', flat=True)
        
        queryset = Invoice.objects.exclude(
            pk__in=service_invoice_ids
        ).select_related(
            'created_by', 'sales_order', 'pos_sale'
        )
        
        # For detail view, prefetch lines and payments
        if self.action == 'retrieve':
            queryset = queryset.prefetch_related('lines', 'payments')
        
        return queryset
    
    def get_serializer_class(self):
        """Use detailed serializer for retrieve, lightweight for list."""
        if self.action == 'retrieve':
            return InvoiceDetailSerializer
        return InvoiceListSerializer
    
    @action(detail=False, methods=['get'])
    def summary(self, request):
        """
        Get invoice summary statistics.
        
        Returns:
        - total_count: Total number of invoices
        - total_amount: Sum of all invoice grand totals
        - paid_count: Number of paid invoices
        - paid_amount: Sum of paid invoice amounts
        - unpaid_count: Number of unpaid invoices
        - unpaid_amount: Sum of unpaid invoice amounts
        - void_count: Number of void invoices
        """
        queryset = self.filter_queryset(self.get_queryset())
        
        # Overall stats
        total_stats = queryset.aggregate(
            count=Coalesce(Sum('id') * 0 + len(queryset), 0),
            total=Coalesce(Sum('grand_total'), Decimal('0'), output_field=DecimalField())
        )
        
        # Paid invoices
        paid_stats = queryset.filter(is_paid=True, is_void=False).aggregate(
            count=Coalesce(Sum('id') * 0 + len(queryset.filter(is_paid=True, is_void=False)), 0),
            total=Coalesce(Sum('grand_total'), Decimal('0'), output_field=DecimalField())
        )
        
        # Unpaid invoices
        unpaid_stats = queryset.filter(is_paid=False, is_void=False).aggregate(
            count=Coalesce(Sum('id') * 0 + len(queryset.filter(is_paid=False, is_void=False)), 0),
            total=Coalesce(Sum('grand_total'), Decimal('0'), output_field=DecimalField())
        )
        
        # Void invoices
        void_count = queryset.filter(is_void=True).count()
        
        return Response({
            'total_count': total_stats['count'],
            'total_amount': total_stats['total'],
            'paid_count': paid_stats['count'],
            'paid_amount': paid_stats['total'],
            'unpaid_count': unpaid_stats['count'],
            'unpaid_amount': unpaid_stats['total'],
            'void_count': void_count,
        })
    
    @action(detail=False, methods=['get'])
    def unpaid(self, request):
        """
        Get list of unpaid invoices.
        Applies same pagination and filtering as main list.
        """
        queryset = self.filter_queryset(
            self.get_queryset().filter(is_paid=False, is_void=False)
        )
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def overdue(self, request):
        """
        Get list of overdue invoices (unpaid with due_date in the past).
        """
        from datetime import date
        today = date.today()
        
        queryset = self.filter_queryset(
            self.get_queryset().filter(
                is_paid=False,
                is_void=False,
                due_date__lt=today
            )
        )
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


class ExpenseFilter(FilterSet):
    """Custom filter for Expense model."""
    
    # Date range filters
    date_from = DateFilter(field_name='date', lookup_expr='gte')
    date_to = DateFilter(field_name='date', lookup_expr='lte')
    
    # Category filter
    category = CharFilter(field_name='category__id')
    
    # Vendor search
    vendor = CharFilter(field_name='vendor', lookup_expr='icontains')
    
    # Status filter
    status = CharFilter(field_name='status')
    
    class Meta:
        model = Expense
        fields = ['date_from', 'date_to', 'category', 'vendor', 'status']


class ExpenseViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API ViewSet for Expenses with pagination and filtering.
    
    Endpoints:
    - GET /api/expenses/ - List all expenses (paginated)
    - GET /api/expenses/{id}/ - Get expense detail
    - GET /api/expenses/summary/ - Get expense summary statistics
    """
    
    queryset = Expense.objects.select_related('category', 'created_by').all()
    serializer_class = ExpenseSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = ExpenseFilter
    search_fields = ['vendor', 'item_description', 'reference_no']
    ordering_fields = ['date', 'amount', 'created_at']
    ordering = ['-date', '-created_at']
    
    @action(detail=False, methods=['get'])
    def summary(self, request):
        """
        Get expense summary statistics.
        
        Returns:
        - total_count: Total number of expenses
        - total_amount: Sum of all expense amounts
        - by_category: Breakdown by category
        - by_status: Breakdown by status
        """
        queryset = self.filter_queryset(self.get_queryset())
        
        # Overall stats
        total_stats = queryset.aggregate(
            count=Coalesce(Sum('id') * 0 + len(queryset), 0),
            total=Coalesce(Sum('amount'), Decimal('0'), output_field=DecimalField())
        )
        
        # By category
        by_category = {}
        for cat in ExpenseCategory.objects.all():
            cat_total = queryset.filter(category=cat).aggregate(
                total=Coalesce(Sum('amount'), Decimal('0'), output_field=DecimalField())
            )['total']
            if cat_total > 0:
                by_category[cat.name] = str(cat_total)
        
        # By status
        by_status = {}
        for status_choice in Expense._meta.get_field('status').choices:
            status_code = status_choice[0]
            status_total = queryset.filter(status=status_code).aggregate(
                total=Coalesce(Sum('amount'), Decimal('0'), output_field=DecimalField())
            )['total']
            if status_total > 0:
                by_status[status_code] = str(status_total)
        
        return Response({
            'total_count': total_stats['count'],
            'total_amount': str(total_stats['total']),
            'by_category': by_category,
            'by_status': by_status,
        })


class ExpenseCategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API ViewSet for Expense Categories.
    
    Endpoints:
    - GET /api/expense-categories/ - List all categories
    - GET /api/expense-categories/{id}/ - Get category detail
    """
    
    queryset = ExpenseCategory.objects.all()
    serializer_class = ExpenseCategorySerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'code']
    ordering_fields = ['name', 'code']
    ordering = ['name']


class SalesChannelViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API ViewSet for Sales Channels.
    
    Endpoints:
    - GET /api/sales-channels/ - List all channels
    - GET /api/sales-channels/{id}/ - Get channel detail
    """
    
    queryset = SalesChannel.objects.all()
    serializer_class = SalesChannelSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'code']
    ordering_fields = ['name', 'code']
    ordering = ['name']
