import 'dart:async';
import 'dart:convert';

import 'package:drift/drift.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:logger/logger.dart';

import '../database/app_database.dart';
import '../services/api_client.dart';
import '../services/connectivity_service.dart';

final _log = Logger();

enum SyncStatus { idle, syncing, error, offline }

class SyncState {
  final SyncStatus status;
  final String? errorMessage;
  final DateTime? lastSyncTime;
  final int pendingChanges;

  const SyncState({
    this.status = SyncStatus.idle,
    this.errorMessage,
    this.lastSyncTime,
    this.pendingChanges = 0,
  });

  SyncState copyWith({
    SyncStatus? status,
    String? errorMessage,
    DateTime? lastSyncTime,
    int? pendingChanges,
  }) {
    return SyncState(
      status: status ?? this.status,
      errorMessage: errorMessage ?? this.errorMessage,
      lastSyncTime: lastSyncTime ?? this.lastSyncTime,
      pendingChanges: pendingChanges ?? this.pendingChanges,
    );
  }
}

class SyncEngine {
  final AppDatabase _db;
  final ApiClient _api;
  final ConnectivityService _connectivity;

  Timer? _periodicSync;
  final _stateController = StreamController<SyncState>.broadcast();
  SyncState _state = const SyncState();

  Stream<SyncState> get stateStream => _stateController.stream;
  SyncState get state => _state;

  SyncEngine(this._db, this._api, this._connectivity) {
    // Auto-sync when connectivity returns
    _connectivity.statusStream.listen((status) {
      if (status == ConnectionStatus.online) {
        syncIfNeeded();
      } else {
        _updateState(_state.copyWith(status: SyncStatus.offline));
      }
    });
  }

  void _updateState(SyncState newState) {
    _state = newState;
    _stateController.add(_state);
  }

  /// Called once after login / app start
  Future<void> initialSync() async {
    if (!_connectivity.isOnline) {
      _updateState(_state.copyWith(status: SyncStatus.offline));
      return;
    }
    await fullSync();
    _startPeriodicSync();
  }

  void _startPeriodicSync() {
    _periodicSync?.cancel();
    _periodicSync = Timer.periodic(
      const Duration(minutes: 5),
      (_) => syncIfNeeded(),
    );
  }

  /// Only sync if online AND not already syncing
  Future<void> syncIfNeeded() async {
    if (!_connectivity.isOnline) return;
    if (_state.status == SyncStatus.syncing) return;
    await fullSync();
  }

  /// Main sync: push local changes, then pull remote changes
  Future<void> fullSync() async {
    try {
      _updateState(_state.copyWith(status: SyncStatus.syncing));

      // 1. Push local changes first (offline-created records)
      await _pushChanges();

      // 2. Pull remote changes
      await _pullChanges();

      // 3. Update state
      final pending = await _db.getPendingChanges(limit: 1);
      _updateState(SyncState(
        status: SyncStatus.idle,
        lastSyncTime: DateTime.now(),
        pendingChanges: pending.length,
      ));

      _log.i('Sync completed successfully');
    } catch (e, stack) {
      _log.e('Sync failed', error: e, stackTrace: stack);
      _updateState(_state.copyWith(
        status: SyncStatus.error,
        errorMessage: e.toString(),
      ));
    }
  }

  // ─── PUSH: Send local changes to server ───

  Future<void> _pushChanges() async {
    final pendingItems = await _db.getPendingChanges(limit: 50);
    if (pendingItems.isEmpty) return;

    // Group by table
    final grouped = <String, List<Map<String, dynamic>>>{};
    for (final item in pendingItems) {
      grouped.putIfAbsent(item.tableName, () => []);
      grouped[item.tableName]!.add({
        'id': item.id,
        'record_id': item.recordId,
        'local_id': item.localId,
        'operation': item.operation,
        'data': jsonDecode(item.payload),
      });
    }

    try {
      final result = await _api.pushChanges({'changes': grouped});

      // Process server responses — map server IDs to local records
      final serverMappings = result['id_mappings'] as Map<String, dynamic>? ?? {};

      for (final entry in serverMappings.entries) {
        // Update local records with server IDs
        await _applyIdMapping(entry.key, entry.value);
      }

      // Remove successfully synced items from queue
      final syncedIds = result['synced_ids'] as List<dynamic>? ?? [];
      for (final id in syncedIds) {
        await _db.removeSyncQueueItem(id as int);
      }
    } catch (e) {
      _log.w('Push failed, will retry later', error: e);
      // Don't rethrow — push failures shouldn't block pull
    }
  }

  Future<void> _applyIdMapping(String table, dynamic mappings) async {
    if (mappings is! List) return;
    for (final mapping in mappings) {
      final localId = mapping['local_id'] as String?;
      final serverId = mapping['server_id'] as int?;
      if (localId == null || serverId == null) continue;

      switch (table) {
        case 'pos_sales':
          await (_db.update(_db.posSales)
                ..where((t) => t.localId.equals(localId)))
              .write(PosSalesCompanion(
                serverId: Value(serverId),
                synced: const Value(true),
              ));
          break;
        case 'pos_shifts':
          await (_db.update(_db.posShifts)
                ..where((t) => t.localId.equals(localId)))
              .write(PosShiftsCompanion(
                serverId: Value(serverId),
                synced: const Value(true),
              ));
          break;
        case 'stock_moves':
          await (_db.update(_db.stockMoves)
                ..where((t) => t.localId.equals(localId)))
              .write(StockMovesCompanion(
                serverId: Value(serverId),
                synced: const Value(true),
              ));
          break;
        case 'sales_orders':
          await (_db.update(_db.salesOrders)
                ..where((t) => t.localId.equals(localId)))
              .write(SalesOrdersCompanion(
                serverId: Value(serverId),
                synced: const Value(true),
              ));
          break;
        case 'cashflow_transactions':
          await (_db.update(_db.cashFlowTransactions)
                ..where((t) => t.localId.equals(localId)))
              .write(CashFlowTransactionsCompanion(
                serverId: Value(serverId),
                synced: const Value(true),
              ));
          break;
      }
    }
  }

  // ─── PULL: Receive remote changes from server ───

  Future<void> _pullChanges() async {
    // Get the oldest last-pull time across all tables
    final lastPull = await _db.getLastPullTime('_global');

    final data = await _api.pullChanges(lastPull);
    final changes = data['changes'] as Map<String, dynamic>? ?? {};
    final timestamp = DateTime.fromMillisecondsSinceEpoch(
      data['timestamp'] as int? ?? DateTime.now().millisecondsSinceEpoch,
    );

    await _db.transaction(() async {
      // Apply each table's changes
      if (changes.containsKey('categories')) {
        await _applyTableChanges('categories', changes['categories'], _upsertCategory);
      }
      if (changes.containsKey('units')) {
        await _applyTableChanges('units', changes['units'], _upsertUnit);
      }
      if (changes.containsKey('items')) {
        await _applyTableChanges('items', changes['items'], _upsertItem);
      }
      if (changes.containsKey('warehouses')) {
        await _applyTableChanges('warehouses', changes['warehouses'], _upsertWarehouse);
      }
      if (changes.containsKey('locations')) {
        await _applyTableChanges('locations', changes['locations'], _upsertLocation);
      }
      if (changes.containsKey('suppliers')) {
        await _applyTableChanges('suppliers', changes['suppliers'], _upsertSupplier);
      }
      if (changes.containsKey('customers')) {
        await _applyTableChanges('customers', changes['customers'], _upsertCustomer);
      }
      if (changes.containsKey('stock_balances')) {
        await _applyTableChanges('stock_balances', changes['stock_balances'], _upsertStockBalance);
      }
      if (changes.containsKey('pos_registers')) {
        await _applyTableChanges('pos_registers', changes['pos_registers'], _upsertPosRegister);
      }
      if (changes.containsKey('price_lists')) {
        await _applyTableChanges('price_lists', changes['price_lists'], _upsertPriceList);
      }
      if (changes.containsKey('price_list_items')) {
        await _applyTableChanges('price_list_items', changes['price_list_items'], _upsertPriceListItem);
      }
      if (changes.containsKey('discount_rules')) {
        await _applyTableChanges('discount_rules', changes['discount_rules'], _upsertDiscountRule);
      }
      if (changes.containsKey('users')) {
        await _applyTableChanges('users', changes['users'], _upsertUser);
      }

      // Update global sync timestamp
      await _db.setLastPullTime('_global', timestamp);
    });
  }

  Future<void> _applyTableChanges(
    String tableName,
    Map<String, dynamic> changes,
    Future<void> Function(Map<String, dynamic>) upsertFn,
  ) async {
    final created = changes['created'] as List<dynamic>? ?? [];
    final updated = changes['updated'] as List<dynamic>? ?? [];
    final deleted = changes['deleted'] as List<dynamic>? ?? [];

    for (final record in created) {
      await upsertFn(record as Map<String, dynamic>);
    }
    for (final record in updated) {
      await upsertFn(record as Map<String, dynamic>);
    }
    // Handle deletes (soft-delete locally)
    for (final id in deleted) {
      await _softDeleteRecord(tableName, id as int);
    }

    await _db.setLastPullTime(tableName, DateTime.now());
  }

  // ─── Upsert functions for each table ───

  Future<void> _upsertCategory(Map<String, dynamic> data) async {
    await _db.into(_db.categories).insertOnConflictUpdate(
          CategoriesCompanion(
            id: Value(data['id']),
            code: Value(data['code']),
            name: Value(data['name']),
            parentId: Value(data['parent']),
            description: Value(data['description'] ?? ''),
            isActive: Value(data['is_active'] ?? true),
            updatedAt: Value(DateTime.now()),
            synced: const Value(true),
          ),
        );
  }

  Future<void> _upsertUnit(Map<String, dynamic> data) async {
    await _db.into(_db.units).insertOnConflictUpdate(
          UnitsCompanion(
            id: Value(data['id']),
            name: Value(data['name']),
            abbreviation: Value(data['abbreviation']),
            category: Value(data['category'] ?? 'quantity'),
            isActive: Value(data['is_active'] ?? true),
            updatedAt: Value(DateTime.now()),
            synced: const Value(true),
          ),
        );
  }

  Future<void> _upsertItem(Map<String, dynamic> data) async {
    await _db.into(_db.items).insertOnConflictUpdate(
          ItemsCompanion(
            id: Value(data['id']),
            code: Value(data['code']),
            name: Value(data['name']),
            itemType: Value(data['item_type'] ?? 'RAW'),
            categoryId: Value(data['category']),
            defaultUnitId: Value(data['default_unit']),
            sellingUnitId: Value(data['selling_unit']),
            description: Value(data['description'] ?? ''),
            barcode: Value(data['barcode'] ?? ''),
            minimumStock: Value((data['minimum_stock'] as num?)?.toDouble() ?? 0),
            maximumStock: Value((data['maximum_stock'] as num?)?.toDouble() ?? 0),
            reorderPoint: Value((data['reorder_point'] as num?)?.toDouble() ?? 0),
            costPrice: Value((data['cost_price'] as num?)?.toDouble() ?? 0),
            sellingPrice: Value((data['selling_price'] as num?)?.toDouble() ?? 0),
            isActive: Value(data['is_active'] ?? true),
            updatedAt: Value(DateTime.now()),
            synced: const Value(true),
          ),
        );
  }

  Future<void> _upsertWarehouse(Map<String, dynamic> data) async {
    await _db.into(_db.warehouses).insertOnConflictUpdate(
          WarehousesCompanion(
            id: Value(data['id']),
            code: Value(data['code']),
            name: Value(data['name']),
            address: Value(data['address'] ?? ''),
            city: Value(data['city'] ?? ''),
            phone: Value(data['phone'] ?? ''),
            managerId: Value(data['manager']),
            allowNegativeStock: Value(data['allow_negative_stock'] ?? false),
            isActive: Value(data['is_active'] ?? true),
            updatedAt: Value(DateTime.now()),
            synced: const Value(true),
          ),
        );
  }

  Future<void> _upsertLocation(Map<String, dynamic> data) async {
    await _db.into(_db.locations).insertOnConflictUpdate(
          LocationsCompanion(
            id: Value(data['id']),
            warehouseId: Value(data['warehouse']),
            code: Value(data['code']),
            name: Value(data['name']),
            parentId: Value(data['parent']),
            locationType: Value(data['location_type'] ?? 'BIN'),
            isPickable: Value(data['is_pickable'] ?? true),
            isActive: Value(data['is_active'] ?? true),
            updatedAt: Value(DateTime.now()),
            synced: const Value(true),
          ),
        );
  }

  Future<void> _upsertSupplier(Map<String, dynamic> data) async {
    await _db.into(_db.suppliers).insertOnConflictUpdate(
          SuppliersCompanion(
            id: Value(data['id']),
            code: Value(data['code']),
            name: Value(data['name']),
            contactPerson: Value(data['contact_person'] ?? ''),
            email: Value(data['email'] ?? ''),
            phone: Value(data['phone'] ?? ''),
            address: Value(data['address'] ?? ''),
            city: Value(data['city'] ?? ''),
            notes: Value(data['notes'] ?? ''),
            isActive: Value(data['is_active'] ?? true),
            updatedAt: Value(DateTime.now()),
            synced: const Value(true),
          ),
        );
  }

  Future<void> _upsertCustomer(Map<String, dynamic> data) async {
    await _db.into(_db.customers).insertOnConflictUpdate(
          CustomersCompanion(
            id: Value(data['id']),
            code: Value(data['code']),
            name: Value(data['name']),
            contactPerson: Value(data['contact_person'] ?? ''),
            email: Value(data['email'] ?? ''),
            phone: Value(data['phone'] ?? ''),
            address: Value(data['address'] ?? ''),
            city: Value(data['city'] ?? ''),
            notes: Value(data['notes'] ?? ''),
            isActive: Value(data['is_active'] ?? true),
            updatedAt: Value(DateTime.now()),
            synced: const Value(true),
          ),
        );
  }

  Future<void> _upsertStockBalance(Map<String, dynamic> data) async {
    await _db.into(_db.stockBalances).insertOnConflictUpdate(
          StockBalancesCompanion(
            id: Value(data['id']),
            itemId: Value(data['item']),
            locationId: Value(data['location']),
            qtyOnHand: Value((data['qty_on_hand'] as num?)?.toDouble() ?? 0),
            qtyReserved: Value((data['qty_reserved'] as num?)?.toDouble() ?? 0),
            updatedAt: Value(DateTime.now()),
            synced: const Value(true),
          ),
        );
  }

  Future<void> _upsertPosRegister(Map<String, dynamic> data) async {
    await _db.into(_db.posRegisters).insertOnConflictUpdate(
          PosRegistersCompanion(
            id: Value(data['id']),
            name: Value(data['name']),
            warehouseId: Value(data['warehouse']),
            defaultLocationId: Value(data['default_location']),
            priceListId: Value(data['price_list']),
            isActive: Value(data['is_active'] ?? true),
            updatedAt: Value(DateTime.now()),
            synced: const Value(true),
          ),
        );
  }

  Future<void> _upsertPriceList(Map<String, dynamic> data) async {
    await _db.into(_db.priceLists).insertOnConflictUpdate(
          PriceListsCompanion(
            id: Value(data['id']),
            name: Value(data['name']),
            warehouseId: Value(data['warehouse']),
            currency: Value(data['currency'] ?? 'PHP'),
            isDefault: Value(data['is_default'] ?? false),
            isActive: Value(data['is_active'] ?? true),
            updatedAt: Value(DateTime.now()),
            synced: const Value(true),
          ),
        );
  }

  Future<void> _upsertPriceListItem(Map<String, dynamic> data) async {
    await _db.into(_db.priceListItems).insertOnConflictUpdate(
          PriceListItemsCompanion(
            id: Value(data['id']),
            priceListId: Value(data['price_list']),
            itemId: Value(data['item']),
            unitId: Value(data['unit']),
            price: Value((data['price'] as num).toDouble()),
            minQty: Value((data['min_qty'] as num?)?.toDouble() ?? 1),
            updatedAt: Value(DateTime.now()),
            synced: const Value(true),
          ),
        );
  }

  Future<void> _upsertDiscountRule(Map<String, dynamic> data) async {
    await _db.into(_db.discountRules).insertOnConflictUpdate(
          DiscountRulesCompanion(
            id: Value(data['id']),
            name: Value(data['name']),
            discountType: Value(data['discount_type']),
            value: Value((data['value'] as num).toDouble()),
            scope: Value(data['scope'] ?? 'ORDER'),
            isActive: Value(data['is_active'] ?? true),
            updatedAt: Value(DateTime.now()),
            synced: const Value(true),
          ),
        );
  }

  Future<void> _upsertUser(Map<String, dynamic> data) async {
    await _db.into(_db.appUsers).insertOnConflictUpdate(
          AppUsersCompanion(
            id: Value(data['id']),
            username: Value(data['username']),
            email: Value(data['email'] ?? ''),
            firstName: Value(data['first_name'] ?? ''),
            lastName: Value(data['last_name'] ?? ''),
            phone: Value(data['phone'] ?? ''),
            isActive: Value(data['is_active'] ?? true),
            updatedAt: Value(DateTime.now()),
            synced: const Value(true),
          ),
        );
  }

  Future<void> _softDeleteRecord(String tableName, int id) async {
    // Soft-delete by setting isActive = false
    switch (tableName) {
      case 'categories':
        await (_db.update(_db.categories)..where((t) => t.id.equals(id)))
            .write(const CategoriesCompanion(isActive: Value(false)));
        break;
      case 'units':
        await (_db.update(_db.units)..where((t) => t.id.equals(id)))
            .write(const UnitsCompanion(isActive: Value(false)));
        break;
      case 'items':
        await (_db.update(_db.items)..where((t) => t.id.equals(id)))
            .write(const ItemsCompanion(isActive: Value(false)));
        break;
      case 'warehouses':
        await (_db.update(_db.warehouses)..where((t) => t.id.equals(id)))
            .write(const WarehousesCompanion(isActive: Value(false)));
        break;
      case 'locations':
        await (_db.update(_db.locations)..where((t) => t.id.equals(id)))
            .write(const LocationsCompanion(isActive: Value(false)));
        break;
      case 'suppliers':
        await (_db.update(_db.suppliers)..where((t) => t.id.equals(id)))
            .write(const SuppliersCompanion(isActive: Value(false)));
        break;
      case 'customers':
        await (_db.update(_db.customers)..where((t) => t.id.equals(id)))
            .write(const CustomersCompanion(isActive: Value(false)));
        break;
    }
  }

  void dispose() {
    _periodicSync?.cancel();
    _stateController.close();
  }
}

// ─── Riverpod Providers ───

final syncEngineProvider = Provider<SyncEngine>((ref) {
  final engine = SyncEngine(
    ref.watch(databaseProvider),
    ref.watch(apiClientProvider),
    ref.watch(connectivityServiceProvider),
  );
  ref.onDispose(() => engine.dispose());
  return engine;
});

final syncStateProvider = StreamProvider<SyncState>((ref) {
  return ref.watch(syncEngineProvider).stateStream;
});
