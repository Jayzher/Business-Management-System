from rest_framework import serializers
from partners.models import Supplier, Customer


class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = [
            'id', 'code', 'name', 'contact_person', 'email', 'phone',
            'address', 'city', 'notes', 'is_active',
        ]


class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = [
            'id', 'code', 'name', 'contact_person', 'email', 'phone',
            'address', 'city', 'notes', 'is_active',
        ]
