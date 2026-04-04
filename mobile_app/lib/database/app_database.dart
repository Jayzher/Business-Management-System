import 'dart:io';

import 'package:drift/drift.dart';
import 'package:drift/native.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';

import 'tables/sync_tables.dart';
import 'tables/catalog_tables.dart';
import 'tables/inventory_tables.dart';
import 'tables/warehouses_tables.dart';
import 'tables/accounts_tables.dart';
import 'tables/partners_tables.dart';
import 'tables/pos_tables.dart';
import 'tables/pricing_tables.dart';
import 'tables/sales_tables.dart';
import 'tables/cashflow_tables.dart';

part 'app_database.g.dart';

@DriftDatabase(tables: [
  // Sync
  SyncMeta,
  SyncQueue,
  // Accounts
  AppUsers,
  Roles,
  UserRoles,
  WarehousePermissions,
  // Catalog
  Categories,
  Units,
  UnitConversions,
  Items,
  MaterialSpecs,
  ProductSpecs,
  // Warehouses
  Warehouses,
  Locations,
  // Partners
  Suppliers,
  Customers,
  // Inventory
  StockMoves,
  StockBalances,
  StockAdjustments,
  StockAdjustmentLines,
  StockTransfers,
  StockTransferLines,
  DamagedReports,
  DamagedReportLines,
  // POS
  PosRegisters,
  PosShifts,
  PosSales,
  PosSaleLines,
  PosPayments,
  PosCashEntries,
  // Pricing
  PriceLists,
  PriceListItems,
  CustomerPriceCatalogs,
  CustomerPriceCatalogItems,
  DiscountRules,
  // Sales
  SalesOrders,
  SalesOrderLines,
  DeliveryNotes,
  DeliveryLines,
  // Cashflow
  CashFlowTransactions,
])
class AppDatabase extends _$AppDatabase {
  AppDatabase() : super(_openConnection());

  // Bump this when you change schema — Drift handles migrations
  @override
  int get schemaVersion => 1;

  @override
  MigrationStrategy get migration => MigrationStrategy(
        onCreate: (Migrator m) async {
          await m.createAll();
        },
        onUpgrade: (Migrator m, int from, int to) async {
          // Add migration steps here as schema evolves
        },
      );

  // ─── Helper: get last sync timestamp for a table ───
  Future<DateTime?> getLastPullTime(String table) async {
    final row = await (select(syncMeta)
          ..where((t) => t.tableName.equals(table)))
        .getSingleOrNull();
    return row?.lastPulledAt;
  }

  Future<void> setLastPullTime(String table, DateTime time) async {
    await into(syncMeta).insertOnConflictUpdate(
      SyncMetaCompanion(
        tableName: Value(table),
        lastPulledAt: Value(time),
      ),
    );
  }

  // ─── Helper: queue a change for push sync ───
  Future<void> queueChange({
    required String tableName,
    int? recordId,
    String? localId,
    required String operation,
    required String payload,
  }) async {
    await into(syncQueue).insert(SyncQueueCompanion(
      tableName: Value(tableName),
      recordId: Value(recordId),
      localId: Value(localId),
      operation: Value(operation),
      payload: Value(payload),
    ));
  }

  // ─── Helper: get all pending sync items ───
  Future<List<SyncQueueData>> getPendingChanges({int limit = 50}) async {
    return (select(syncQueue)
          ..where((t) => t.retryCount.isSmallerThanValue(3))
          ..orderBy([(t) => OrderingTerm.asc(t.createdAt)])
          ..limit(limit))
        .get();
  }

  // ─── Helper: mark sync item as done ───
  Future<void> removeSyncQueueItem(int id) async {
    await (delete(syncQueue)..where((t) => t.id.equals(id))).go();
  }

  // ─── Helper: increment retry count ───
  Future<void> incrementRetryCount(int id, String error) async {
    final item = await (select(syncQueue)..where((t) => t.id.equals(id)))
        .getSingleOrNull();
    final currentCount = item?.retryCount ?? 0;
    await (update(syncQueue)..where((t) => t.id.equals(id))).write(
      SyncQueueCompanion(
        retryCount: Value(currentCount + 1),
        errorMessage: Value(error),
      ),
    );
  }
}

LazyDatabase _openConnection() {
  return LazyDatabase(() async {
    final dbFolder = await getApplicationDocumentsDirectory();
    final file = File(p.join(dbFolder.path, 'business_app.sqlite'));
    return NativeDatabase.createInBackground(file);
  });
}

// ─── Riverpod Provider ───

final databaseProvider = Provider<AppDatabase>((ref) {
  final db = AppDatabase();
  ref.onDispose(() => db.close());
  return db;
});
