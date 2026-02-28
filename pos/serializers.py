from rest_framework import serializers
from pos.models import (
    POSRegister, POSShift, POSSale, POSSaleLine,
    POSPayment, POSRefund, POSRefundLine, CashEntry,
)


class POSRegisterSerializer(serializers.ModelSerializer):
    warehouse_name = serializers.CharField(source='warehouse.name', read_only=True)
    location_code = serializers.CharField(source='default_location.code', read_only=True)

    class Meta:
        model = POSRegister
        fields = [
            'id', 'name', 'warehouse', 'warehouse_name',
            'default_location', 'location_code',
            'price_list', 'receipt_footer', 'is_active',
        ]


class POSShiftSerializer(serializers.ModelSerializer):
    register_name = serializers.CharField(source='register.name', read_only=True)
    opened_by_name = serializers.CharField(source='opened_by.get_full_name', read_only=True)
    expected_cash = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)
    variance = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)

    class Meta:
        model = POSShift
        fields = [
            'id', 'register', 'register_name',
            'opened_by', 'opened_by_name', 'opened_at', 'opening_cash',
            'closed_by', 'closed_at', 'closing_cash_declared',
            'status',
            'cash_sales_total', 'noncash_sales_total',
            'refund_total', 'cash_in_out_total',
            'expected_cash', 'variance',
        ]
        read_only_fields = [
            'id', 'opened_by', 'opened_at',
            'closed_by', 'closed_at',
            'cash_sales_total', 'noncash_sales_total',
            'refund_total', 'cash_in_out_total',
        ]


class POSSaleLineSerializer(serializers.ModelSerializer):
    item_code = serializers.CharField(source='item.code', read_only=True)
    item_name = serializers.CharField(source='item.name', read_only=True)
    unit_abbr = serializers.CharField(source='unit.abbreviation', read_only=True)

    class Meta:
        model = POSSaleLine
        fields = [
            'id', 'item', 'item_code', 'item_name',
            'location', 'qty', 'unit', 'unit_abbr',
            'unit_price', 'discount_amount', 'tax_rate', 'line_total',
            'batch_number', 'serial_number', 'qr_uid_used',
        ]


class POSPaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = POSPayment
        fields = ['id', 'sale', 'method', 'amount', 'reference_no', 'paid_at']
        read_only_fields = ['id', 'paid_at']


class POSSaleSerializer(serializers.ModelSerializer):
    lines = POSSaleLineSerializer(many=True, read_only=True)
    payments = POSPaymentSerializer(many=True, read_only=True)
    register_name = serializers.CharField(source='register.name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)

    class Meta:
        model = POSSale
        fields = [
            'id', 'sale_no', 'register', 'register_name',
            'shift', 'warehouse', 'location',
            'customer', 'status',
            'subtotal', 'discount_total', 'tax_total', 'grand_total',
            'created_by', 'created_by_name',
            'posted_by', 'posted_at',
            'notes', 'created_at',
            'lines', 'payments',
        ]
        read_only_fields = [
            'id', 'sale_no', 'status',
            'subtotal', 'discount_total', 'tax_total', 'grand_total',
            'created_by', 'posted_by', 'posted_at', 'created_at',
        ]


class POSRefundLineSerializer(serializers.ModelSerializer):
    item_code = serializers.CharField(source='item.code', read_only=True)
    item_name = serializers.CharField(source='item.name', read_only=True)

    class Meta:
        model = POSRefundLine
        fields = [
            'id', 'sale_line', 'item', 'item_code', 'item_name',
            'location', 'qty', 'unit', 'amount',
        ]


class POSRefundSerializer(serializers.ModelSerializer):
    lines = POSRefundLineSerializer(many=True, read_only=True)
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)

    class Meta:
        model = POSRefund
        fields = [
            'id', 'refund_no', 'original_sale', 'shift', 'status',
            'subtotal', 'tax_total', 'grand_total', 'reason',
            'created_by', 'created_by_name',
            'posted_by', 'posted_at', 'created_at',
            'lines',
        ]
        read_only_fields = [
            'id', 'refund_no', 'status',
            'subtotal', 'tax_total', 'grand_total',
            'created_by', 'posted_by', 'posted_at', 'created_at',
        ]


class CashEntrySerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)

    class Meta:
        model = CashEntry
        fields = [
            'id', 'shift', 'entry_type', 'amount', 'reason',
            'created_by', 'created_by_name', 'created_at',
        ]
        read_only_fields = ['id', 'created_by', 'created_at']


# ── Request serializers for actions ────────────────────────────────────────

class OpenShiftRequestSerializer(serializers.Serializer):
    register = serializers.IntegerField()
    opening_cash = serializers.DecimalField(max_digits=15, decimal_places=2, default=0)


class CloseShiftRequestSerializer(serializers.Serializer):
    closing_cash_declared = serializers.DecimalField(max_digits=15, decimal_places=2)


class AddLineRequestSerializer(serializers.Serializer):
    item = serializers.IntegerField()
    qty = serializers.DecimalField(max_digits=15, decimal_places=4)
    unit = serializers.IntegerField()
    unit_price = serializers.DecimalField(max_digits=15, decimal_places=4)
    discount_amount = serializers.DecimalField(max_digits=15, decimal_places=2, default=0)
    tax_rate = serializers.DecimalField(max_digits=5, decimal_places=2, default=0)
    location = serializers.IntegerField(required=False, allow_null=True)
    batch_number = serializers.CharField(required=False, default='')
    serial_number = serializers.CharField(required=False, default='')
    qr_uid_used = serializers.UUIDField(required=False, allow_null=True)


class SetPaymentsRequestSerializer(serializers.Serializer):
    payments = POSPaymentSerializer(many=True)


class CreateRefundRequestSerializer(serializers.Serializer):
    original_sale = serializers.IntegerField()
    reason = serializers.CharField(required=False, default='')
    lines = POSRefundLineSerializer(many=True)
