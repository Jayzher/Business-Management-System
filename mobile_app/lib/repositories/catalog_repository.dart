import 'package:drift/drift.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../database/app_database.dart';

class CatalogRepository {
  final AppDatabase _db;

  CatalogRepository(this._db);

  // ─── Items ───

  Stream<List<Item>> watchItems({String? search, String? itemType, bool activeOnly = true}) {
    final query = _db.select(_db.items);
    if (activeOnly) query.where((t) => t.isActive.equals(true));
    if (itemType != null) query.where((t) => t.itemType.equals(itemType));
    if (search != null && search.isNotEmpty) {
      query.where((t) =>
          t.name.contains(search) |
          t.code.contains(search) |
          t.barcode.contains(search));
    }
    query.orderBy([(t) => OrderingTerm.asc(t.code)]);
    return query.watch();
  }

  Future<Item?> getItemById(int id) {
    return (_db.select(_db.items)..where((t) => t.id.equals(id))).getSingleOrNull();
  }

  Future<Item?> getItemByBarcode(String barcode) {
    return (_db.select(_db.items)
          ..where((t) => t.barcode.equals(barcode) & t.isActive.equals(true)))
        .getSingleOrNull();
  }

  // ─── Categories ───

  Stream<List<Category>> watchCategories() {
    return (_db.select(_db.categories)
          ..where((t) => t.isActive.equals(true))
          ..orderBy([(t) => OrderingTerm.asc(t.name)]))
        .watch();
  }

  // ─── Units ───

  Stream<List<Unit>> watchUnits() {
    return (_db.select(_db.units)
          ..where((t) => t.isActive.equals(true))
          ..orderBy([(t) => OrderingTerm.asc(t.name)]))
        .watch();
  }

  Future<Unit?> getUnitById(int id) {
    return (_db.select(_db.units)..where((t) => t.id.equals(id))).getSingleOrNull();
  }

  // ─── Unit Conversions ───

  Future<List<UnitConversion>> getConversionsForItem(int itemId) {
    return (_db.select(_db.unitConversions)
          ..where((t) =>
              t.itemId.equals(itemId) | t.itemId.isNull()))
        .get();
  }

  Future<double?> getConversionFactor(int fromUnitId, int toUnitId, {int? itemId}) async {
    // Try item-specific first
    if (itemId != null) {
      final specific = await (_db.select(_db.unitConversions)
            ..where((t) =>
                t.fromUnitId.equals(fromUnitId) &
                t.toUnitId.equals(toUnitId) &
                t.itemId.equals(itemId)))
          .getSingleOrNull();
      if (specific != null) return specific.factor;
    }

    // Fall back to global
    final global = await (_db.select(_db.unitConversions)
          ..where((t) =>
              t.fromUnitId.equals(fromUnitId) &
              t.toUnitId.equals(toUnitId) &
              t.itemId.isNull()))
        .getSingleOrNull();
    return global?.factor;
  }
}

final catalogRepositoryProvider = Provider<CatalogRepository>((ref) {
  return CatalogRepository(ref.watch(databaseProvider));
});
