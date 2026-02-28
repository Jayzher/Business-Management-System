from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import redirect
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from accounts.views import (
    UserViewSet, RoleViewSet, UserRoleViewSet, WarehousePermissionViewSet, me,
)
from catalog.views import CategoryViewSet, UnitViewSet, UnitConversionViewSet, ItemViewSet
from partners.views import SupplierViewSet, CustomerViewSet
from warehouses.views import WarehouseViewSet, LocationViewSet
from inventory.views import (
    StockMoveViewSet, StockBalanceViewSet,
    StockTransferViewSet, StockAdjustmentViewSet, DamagedReportViewSet,
)
from procurement.views import PurchaseOrderViewSet, GoodsReceiptViewSet
from sales.views import SalesOrderViewSet, DeliveryNoteViewSet
from qr.views import QRCodeTagViewSet, generate_qr, qr_lookup, qr_scan
from reports.views import (
    stock_on_hand_report, stock_movement_report,
    damaged_summary_report, low_stock_report,
)
from pricing.views import PriceListViewSet, PriceListItemViewSet, DiscountRuleViewSet, price_lookup
from pos.views import (
    POSRegisterViewSet, POSShiftViewSet, POSSaleViewSet,
    POSRefundViewSet, CashEntryViewSet,
    api_open_shift, api_close_shift, api_shift_summary,
)
from theme.views import dashboard_view

# ── DRF Router ─────────────────────────────────────────────────────────────
router = DefaultRouter()
router.register(r'users', UserViewSet)
router.register(r'roles', RoleViewSet)
router.register(r'user-roles', UserRoleViewSet)
router.register(r'warehouse-permissions', WarehousePermissionViewSet)
router.register(r'categories', CategoryViewSet)
router.register(r'units', UnitViewSet)
router.register(r'unit-conversions', UnitConversionViewSet)
router.register(r'items', ItemViewSet)
router.register(r'suppliers', SupplierViewSet)
router.register(r'customers', CustomerViewSet)
router.register(r'warehouses', WarehouseViewSet)
router.register(r'locations', LocationViewSet)
router.register(r'stock-moves', StockMoveViewSet)
router.register(r'stock-balances', StockBalanceViewSet)
router.register(r'transfers', StockTransferViewSet)
router.register(r'adjustments', StockAdjustmentViewSet)
router.register(r'damaged-reports', DamagedReportViewSet)
router.register(r'purchase-orders', PurchaseOrderViewSet)
router.register(r'goods-receipts', GoodsReceiptViewSet)
router.register(r'sales-orders', SalesOrderViewSet)
router.register(r'deliveries', DeliveryNoteViewSet)
router.register(r'qr-tags', QRCodeTagViewSet)
router.register(r'price-lists', PriceListViewSet)
router.register(r'price-list-items', PriceListItemViewSet)
router.register(r'discount-rules', DiscountRuleViewSet)
router.register(r'pos/registers', POSRegisterViewSet)
router.register(r'pos/shifts', POSShiftViewSet, basename='pos-shift')
router.register(r'pos/sales', POSSaleViewSet, basename='pos-sale')
router.register(r'pos/refunds', POSRefundViewSet, basename='pos-refund')
router.register(r'pos/cash-entries', CashEntryViewSet, basename='pos-cashentry')

urlpatterns = [
    # Root redirect
    path('', lambda request: redirect('dashboard')),

    # Admin
    path('admin/', admin.site.urls),

    # Auth (JWT)
    path('api/auth/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/users/me/', me, name='api_me'),

    # API (DRF Router)
    path('api/', include(router.urls)),

    # QR API endpoints
    path('api/qr/generate/', generate_qr, name='api_qr_generate'),
    path('api/qr/<uuid:uid>/', qr_lookup, name='api_qr_lookup'),
    path('api/qr/scan/', qr_scan, name='api_qr_scan'),

    # POS API endpoints
    path('api/pos/shifts/open/', api_open_shift, name='api_pos_shift_open'),
    path('api/pos/shifts/<int:pk>/close/', api_close_shift, name='api_pos_shift_close'),
    path('api/pos/shifts/<int:pk>/summary/', api_shift_summary, name='api_pos_shift_summary'),

    # Pricing API endpoints
    path('api/pricing/price/', price_lookup, name='api_price_lookup'),

    # Report API endpoints
    path('api/reports/stock-on-hand/', stock_on_hand_report, name='api_stock_on_hand'),
    path('api/reports/stock-movement/', stock_movement_report, name='api_stock_movement'),
    path('api/reports/damaged-summary/', damaged_summary_report, name='api_damaged_summary'),
    path('api/reports/low-stock/', low_stock_report, name='api_low_stock'),

    # Template views
    path('dashboard/', dashboard_view, name='dashboard'),
    path('accounts/', include('accounts.urls')),
    path('catalog/', include('catalog.urls')),
    path('partners/', include('partners.urls')),
    path('warehouses/', include('warehouses.urls')),
    path('inventory/', include('inventory.urls')),
    path('procurement/', include('procurement.urls')),
    path('sales/', include('sales.urls')),
    path('qr/', include('qr.urls')),
    path('reports/', include('reports.urls')),
    path('pricing/', include('pricing.urls')),
    path('pos/', include('pos.urls')),
    path('core/', include('core.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
