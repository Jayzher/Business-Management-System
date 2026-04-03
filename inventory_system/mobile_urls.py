"""
Mobile API URL configuration — API-only, no web views/admin.
Serves the Flutter mobile app with JWT auth + sync endpoints.
"""

from django.urls import path, include
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from accounts.views import UserViewSet, RoleViewSet, WarehousePermissionViewSet, me
from catalog.views import CategoryViewSet, UnitViewSet, UnitConversionViewSet, ItemViewSet
from partners.views import SupplierViewSet, CustomerViewSet
from warehouses.views import WarehouseViewSet, LocationViewSet
from inventory.views import (
    StockMoveViewSet, StockBalanceViewSet,
    StockTransferViewSet, StockAdjustmentViewSet, DamagedReportViewSet,
)
from sales.views import SalesOrderViewSet, DeliveryNoteViewSet
from pricing.views import PriceListViewSet, PriceListItemViewSet, DiscountRuleViewSet, price_lookup
from pos.views import (
    POSRegisterViewSet, POSShiftViewSet, POSSaleViewSet,
    POSRefundViewSet, CashEntryViewSet,
    api_open_shift, api_close_shift, api_shift_summary,
)


# ─── Health check ──────────────────────────────────────────────────────────
@api_view(['GET'])
@permission_classes([AllowAny])
def health_check(request):
    return Response({'status': 'ok', 'service': 'mobile-api'})


# ─── DRF Router (API only) ────────────────────────────────────────────────
router = DefaultRouter()

# Accounts
router.register(r'users', UserViewSet)
router.register(r'roles', RoleViewSet)
router.register(r'warehouse-permissions', WarehousePermissionViewSet)

# Catalog
router.register(r'categories', CategoryViewSet)
router.register(r'units', UnitViewSet)
router.register(r'unit-conversions', UnitConversionViewSet)
router.register(r'items', ItemViewSet)

# Partners
router.register(r'suppliers', SupplierViewSet)
router.register(r'customers', CustomerViewSet)

# Warehouses
router.register(r'warehouses', WarehouseViewSet)
router.register(r'locations', LocationViewSet)

# Inventory
router.register(r'stock-moves', StockMoveViewSet)
router.register(r'stock-balances', StockBalanceViewSet)
router.register(r'transfers', StockTransferViewSet)
router.register(r'adjustments', StockAdjustmentViewSet)
router.register(r'damaged-reports', DamagedReportViewSet)

# Sales
router.register(r'sales-orders', SalesOrderViewSet)
router.register(r'deliveries', DeliveryNoteViewSet)

# Pricing
router.register(r'price-lists', PriceListViewSet)
router.register(r'price-list-items', PriceListItemViewSet)
router.register(r'discount-rules', DiscountRuleViewSet)

# POS
router.register(r'pos/registers', POSRegisterViewSet)
router.register(r'pos/shifts', POSShiftViewSet, basename='pos-shift')
router.register(r'pos/sales', POSSaleViewSet, basename='pos-sale')
router.register(r'pos/refunds', POSRefundViewSet, basename='pos-refund')
router.register(r'pos/cash-entries', CashEntryViewSet, basename='pos-cashentry')


urlpatterns = [
    # Health check (no auth)
    path('api/health/', health_check, name='health_check'),

    # Auth (JWT)
    path('api/accounts/token/', TokenObtainPairView.as_view(), name='token_obtain'),
    path('api/accounts/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/users/me/', me, name='api_me'),

    # Sync endpoints (offline-first: pull from Neon DB, push local changes)
    path('api/sync/', include('sync.urls')),

    # REST API endpoints (same data from Neon DB)
    path('api/', include(router.urls)),

    # POS action endpoints
    path('api/pos/shifts/open/', api_open_shift, name='api_pos_shift_open'),
    path('api/pos/shifts/<int:pk>/close/', api_close_shift, name='api_pos_shift_close'),
    path('api/pos/shifts/<int:pk>/summary/', api_shift_summary, name='api_pos_shift_summary'),

    # Pricing
    path('api/pricing/price/', price_lookup, name='api_price_lookup'),
]
