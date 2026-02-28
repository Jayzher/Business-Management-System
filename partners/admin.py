from django.contrib import admin
from partners.models import Supplier, Customer


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'contact_person', 'email', 'phone', 'city', 'is_active']
    list_filter = ['is_active', 'city']
    search_fields = ['code', 'name', 'contact_person', 'email']


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'contact_person', 'email', 'phone', 'city', 'is_active']
    list_filter = ['is_active', 'city']
    search_fields = ['code', 'name', 'contact_person', 'email']
