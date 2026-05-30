"""
Serializers for core app models (Invoice, Expense, etc.)
"""
from rest_framework import serializers
from decimal import Decimal

from core.models import (
    Invoice, InvoiceLine, InvoicePayment,
    Expense, ExpenseCategory,
    SalesChannel, BusinessProfile,
)


class InvoiceLineSerializer(serializers.ModelSerializer):
    """Serializer for Invoice Line Items."""
    
    class Meta:
        model = InvoiceLine
        fields = [
            'id', 'item_code', 'item_name', 'qty', 'unit',
            'unit_price', 'discount', 'line_total'
        ]


class InvoicePaymentSerializer(serializers.ModelSerializer):
    """Serializer for Invoice Payments."""
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    
    class Meta:
        model = InvoicePayment
        fields = [
            'id', 'date', 'method', 'amount', 'reference_no',
            'notes', 'created_at', 'created_by_name'
        ]


class InvoiceListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for invoice list view."""
    customer_name = serializers.CharField()
    payment_status = serializers.CharField(read_only=True)
    total_paid = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)
    balance_due = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    sales_order_number = serializers.CharField(source='sales_order.document_number', read_only=True)
    pos_sale_number = serializers.CharField(source='pos_sale.sale_no', read_only=True)
    
    class Meta:
        model = Invoice
        fields = [
            'id', 'invoice_number', 'date', 'due_date',
            'customer_name', 'grand_total', 'payment_status',
            'total_paid', 'balance_due', 'is_paid', 'is_void',
            'created_at', 'created_by_name',
            'sales_order_number', 'pos_sale_number'
        ]


class InvoiceDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for invoice detail view with lines and payments."""
    lines = InvoiceLineSerializer(many=True, read_only=True)
    payments = InvoicePaymentSerializer(many=True, read_only=True)
    payment_status = serializers.CharField(read_only=True)
    total_paid = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)
    balance_due = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    sales_order_number = serializers.CharField(source='sales_order.document_number', read_only=True)
    pos_sale_number = serializers.CharField(source='pos_sale.sale_no', read_only=True)
    
    class Meta:
        model = Invoice
        fields = [
            'id', 'invoice_number', 'date', 'due_date',
            'pos_sale', 'sales_order', 'pos_sale_number', 'sales_order_number',
            'customer_name', 'customer_address', 'customer_tin',
            'subtotal', 'discount_total', 'tax_total', 'delivery_charge',
            'grand_total', 'grand_total_cogs', 'notes',
            'is_paid', 'paid_at', 'paid_date', 'is_void', 'void_reason',
            'payment_status', 'total_paid', 'balance_due',
            'created_at', 'updated_at', 'created_by_name',
            'lines', 'payments'
        ]


class ExpenseCategorySerializer(serializers.ModelSerializer):
    """Serializer for Expense Categories."""
    
    class Meta:
        model = ExpenseCategory
        fields = ['id', 'name', 'code', 'description', 'is_cogs', 'is_active']


class ExpenseSerializer(serializers.ModelSerializer):
    """Serializer for Expenses."""
    category_name = serializers.CharField(source='category.name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    
    class Meta:
        model = Expense
        fields = [
            'id', 'date', 'category', 'category_name', 'item_description',
            'amount', 'status', 'vendor', 'business_address', 'reference_no',
            'receipt_photo', 'memo', 'created_at', 'created_by_name'
        ]


class SalesChannelSerializer(serializers.ModelSerializer):
    """Serializer for Sales Channels."""
    
    class Meta:
        model = SalesChannel
        fields = ['id', 'name', 'code', 'description', 'is_active']


class BusinessProfileSerializer(serializers.ModelSerializer):
    """Serializer for Business Profile."""
    
    class Meta:
        model = BusinessProfile
        fields = [
            'id', 'name', 'tagline', 'owner_name', 'email', 'phone',
            'address', 'city', 'province', 'zip_code', 'country', 'tin',
            'logo', 'currency', 'fiscal_year_start_month', 'receipt_footer'
        ]
