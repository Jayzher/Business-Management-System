import 'package:drift/drift.dart';

import 'catalog_tables.dart';
import 'warehouses_tables.dart';
import 'accounts_tables.dart';

// ─── Stock Move ───

class StockMoves extends Table {
  IntColumn get id => integer().autoIncrement()();
  TextColumn get localId => text().nullable()(); // UUID for offline-created
  IntColumn get serverId => integer().nullable()(); // Server ID after sync
  TextColumn get moveType => text()();
  IntColumn get itemId => integer().references(Items, #id)();
  RealColumn get qty => real()();
  IntColumn get unitId => integer().references(Units, #id)();
  IntColumn get fromLocationId => integer().nullable().references(Locations, #id)();
  IntColumn get toLocationId => integer().nullable().references(Locations, #id)();
  TextColumn get referenceType => text().withDefault(const Constant(''))();
  IntColumn get referenceId => integer().nullable()();
  TextColumn get referenceNumber => text().withDefault(const Constant(''))();
  TextColumn get status => text().withDefault(const Constant('DRAFT'))();
  TextColumn get batchNumber => text().withDefault(const Constant(''))();
  TextColumn get serialNumber => text().withDefault(const Constant(''))();
  TextColumn get notes => text().withDefault(const Constant(''))();
  IntColumn get createdById => integer().references(AppUsers, #id)();
  IntColumn get postedById => integer().nullable().references(AppUsers, #id)();
  DateTimeColumn get createdAt => dateTime().withDefault(currentDateAndTime)();
  DateTimeColumn get postedAt => dateTime().nullable()();
  BoolColumn get synced => boolean().withDefault(const Constant(false))();
}

// ─── Stock Balance ───

class StockBalances extends Table {
  IntColumn get id => integer()();
  IntColumn get itemId => integer().references(Items, #id)();
  IntColumn get locationId => integer().references(Locations, #id)();
  RealColumn get qtyOnHand => real().withDefault(const Constant(0))();
  RealColumn get qtyReserved => real().withDefault(const Constant(0))();
  DateTimeColumn get updatedAt => dateTime().withDefault(currentDateAndTime)();
  BoolColumn get synced => boolean().withDefault(const Constant(true))();

  @override
  Set<Column> get primaryKey => {id};
}

// ─── Stock Adjustment ───

class StockAdjustments extends Table {
  IntColumn get id => integer().autoIncrement()();
  TextColumn get localId => text().nullable()();
  IntColumn get serverId => integer().nullable()();
  TextColumn get documentNumber => text().withDefault(const Constant(''))();
  TextColumn get status => text().withDefault(const Constant('DRAFT'))();
  IntColumn get warehouseId => integer().references(Warehouses, #id)();
  TextColumn get reason => text().withDefault(const Constant(''))();
  TextColumn get notes => text().withDefault(const Constant(''))();
  IntColumn get createdById => integer().references(AppUsers, #id)();
  DateTimeColumn get createdAt => dateTime().withDefault(currentDateAndTime)();
  BoolColumn get synced => boolean().withDefault(const Constant(false))();
}

class StockAdjustmentLines extends Table {
  IntColumn get id => integer().autoIncrement()();
  IntColumn get adjustmentId => integer().references(StockAdjustments, #id)();
  IntColumn get itemId => integer().references(Items, #id)();
  IntColumn get locationId => integer().references(Locations, #id)();
  RealColumn get qtyCounted => real()();
  RealColumn get qtySystem => real().withDefault(const Constant(0))();
  IntColumn get unitId => integer().references(Units, #id)();
  TextColumn get batchNumber => text().withDefault(const Constant(''))();
  TextColumn get notes => text().withDefault(const Constant(''))();
}

// ─── Stock Transfer ───

class StockTransfers extends Table {
  IntColumn get id => integer().autoIncrement()();
  TextColumn get localId => text().nullable()();
  IntColumn get serverId => integer().nullable()();
  TextColumn get documentNumber => text().withDefault(const Constant(''))();
  TextColumn get status => text().withDefault(const Constant('DRAFT'))();
  IntColumn get fromWarehouseId => integer().references(Warehouses, #id)();
  IntColumn get toWarehouseId => integer().references(Warehouses, #id)();
  TextColumn get notes => text().withDefault(const Constant(''))();
  IntColumn get createdById => integer().references(AppUsers, #id)();
  DateTimeColumn get createdAt => dateTime().withDefault(currentDateAndTime)();
  BoolColumn get synced => boolean().withDefault(const Constant(false))();
}

class StockTransferLines extends Table {
  IntColumn get id => integer().autoIncrement()();
  IntColumn get transferId => integer().references(StockTransfers, #id)();
  IntColumn get itemId => integer().references(Items, #id)();
  IntColumn get fromLocationId => integer().references(Locations, #id)();
  IntColumn get toLocationId => integer().references(Locations, #id)();
  RealColumn get qty => real()();
  IntColumn get unitId => integer().references(Units, #id)();
  TextColumn get batchNumber => text().withDefault(const Constant(''))();
  TextColumn get serialNumber => text().withDefault(const Constant(''))();
  TextColumn get notes => text().withDefault(const Constant(''))();
}

// ─── Damaged Report ───

class DamagedReports extends Table {
  IntColumn get id => integer().autoIncrement()();
  TextColumn get localId => text().nullable()();
  IntColumn get serverId => integer().nullable()();
  TextColumn get documentNumber => text().withDefault(const Constant(''))();
  TextColumn get status => text().withDefault(const Constant('DRAFT'))();
  IntColumn get warehouseId => integer().references(Warehouses, #id)();
  TextColumn get notes => text().withDefault(const Constant(''))();
  IntColumn get createdById => integer().references(AppUsers, #id)();
  DateTimeColumn get createdAt => dateTime().withDefault(currentDateAndTime)();
  BoolColumn get synced => boolean().withDefault(const Constant(false))();
}

class DamagedReportLines extends Table {
  IntColumn get id => integer().autoIncrement()();
  IntColumn get reportId => integer().references(DamagedReports, #id)();
  IntColumn get itemId => integer().references(Items, #id)();
  IntColumn get locationId => integer().references(Locations, #id)();
  RealColumn get qty => real()();
  IntColumn get unitId => integer().references(Units, #id)();
  TextColumn get batchNumber => text().withDefault(const Constant(''))();
  TextColumn get reason => text().withDefault(const Constant(''))();
  TextColumn get photoPath => text().nullable()();
  TextColumn get notes => text().withDefault(const Constant(''))();
}
