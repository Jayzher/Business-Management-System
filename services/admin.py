from django.contrib import admin
from services.models import CustomerService, ServiceLine


class ServiceLineInline(admin.TabularInline):
    model = ServiceLine
    extra = 0
    readonly_fields = ('line_total',)


@admin.register(CustomerService)
class CustomerServiceAdmin(admin.ModelAdmin):
    list_display = (
        'service_number', 'service_name', 'customer_name',
        'service_date', 'status', 'payment_status', 'grand_total',
    )
    list_filter = ('status', 'payment_status')
    search_fields = ('service_number', 'service_name', 'customer_name')
    readonly_fields = ('created_at', 'updated_at', 'posted_at', 'grand_total')
    inlines = [ServiceLineInline]
