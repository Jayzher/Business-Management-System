class ApiConfig {
  // Change this to your Django server URL
  static const String baseUrl = 'http://10.0.2.2:8000/api'; // Android emulator → localhost
  static const String baseUrlIOS = 'http://localhost:8000/api';

  static const Duration connectTimeout = Duration(seconds: 15);
  static const Duration receiveTimeout = Duration(seconds: 30);

  // Sync settings
  static const Duration syncInterval = Duration(minutes: 5);
  static const int maxRetries = 3;
  static const int syncBatchSize = 100;

  // Endpoints
  static const String tokenEndpoint = '/accounts/token/';
  static const String tokenRefreshEndpoint = '/accounts/token/refresh/';
  static const String syncPullEndpoint = '/sync/pull/';
  static const String syncPushEndpoint = '/sync/push/';

  // Feature endpoints
  static const String itemsEndpoint = '/catalog/items/';
  static const String categoriesEndpoint = '/catalog/categories/';
  static const String unitsEndpoint = '/catalog/units/';
  static const String unitConversionsEndpoint = '/catalog/unit-conversions/';
  static const String suppliersEndpoint = '/partners/suppliers/';
  static const String customersEndpoint = '/partners/customers/';
  static const String warehousesEndpoint = '/warehouses/';
  static const String locationsEndpoint = '/warehouses/locations/';
  static const String stockBalancesEndpoint = '/inventory/balances/';
  static const String stockMovesEndpoint = '/inventory/moves/';
  static const String posRegisterEndpoint = '/pos/registers/';
  static const String posShiftEndpoint = '/pos/shifts/';
  static const String posSalesEndpoint = '/pos/sales/';
  static const String priceListsEndpoint = '/pricing/price-lists/';
  static const String salesOrdersEndpoint = '/sales/orders/';
}
