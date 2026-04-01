import 'package:drift/drift.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../database/app_database.dart';

class InventoryRepository {
  final AppDatabase _db;

  InventoryRepository(this._db);

  // ─── Stock Balances ───

  Stream<List<StockBalance>> watchBalances({int? warehouseId, int? itemId}) {
    final query = _db.select(_db.stockBalances).join([
      innerJoin(_db.locations, _db.locations.id.equalsExp(_db.stockBalances.locationId)),
    ]);

    if (warehouseId != null) {
      query.where(_db.locations.warehouseId.equals(warehouseId));
    }
    if (itemId != null) {
      query.where(_db.stockBalances.itemId.equals(itemId));
    }

    return query.map((row) => row.readTable(_db.stockBalances)).watch();
  }

  Future<double> getAvailableQty(int itemId, {int? locationId}) async {
    if (locationId != null) {
      final balance = await (_db.select(_db.stockBalances)
            ..where((t) =>
                t.itemId.equals(itemId) & t.locationId.equals(locationId)))
          .getSingleOrNull();
      return (balance?.qtyOnHand ?? 0) - (balance?.qtyReserved ?? 0);
    }

    // Sum across all locations
    final result = await _db.customSelect(
      'SELECT COALESCE(SUM(qty_on_hand - qty_reserved), 0) as total '
      'FROM stock_balances WHERE item_id = ?',
      variables: [Variable.withInt(itemId)],
    ).getSingle();
    return result.read<double>('total');
  }

  // ─── Stock Moves ───

  Stream<List<StockMove>> watchRecentMoves({int limit = 50}) {
    return (_db.select(_db.stockMoves)
          ..orderBy([(t) => OrderingTerm.desc(t.createdAt)])
          ..limit(limit))
        .watch();
  }

  // ─── Warehouses ───

  Stream<List<Warehouse>> watchWarehouses() {
    return (_db.select(_db.warehouses)
          ..where((t) => t.isActive.equals(true))
          ..orderBy([(t) => OrderingTerm.asc(t.code)]))
        .watch();
  }

  Future<Warehouse?> getWarehouseById(int id) {
    return (_db.select(_db.warehouses)..where((t) => t.id.equals(id))).getSingleOrNull();
  }

  // ─── Locations ───

  Stream<List<Location>> watchLocations(int warehouseId) {
    return (_db.select(_db.locations)
          ..where((t) => t.warehouseId.equals(warehouseId) & t.isActive.equals(true))
          ..orderBy([(t) => OrderingTerm.asc(t.code)]))
        .watch();
  }
}

final inventoryRepositoryProvider = Provider<InventoryRepository>((ref) {
  return InventoryRepository(ref.watch(databaseProvider));
});
