import 'package:drift/drift.dart';

// ─── Warehouse ───

class Warehouses extends Table {
  IntColumn get id => integer()();
  TextColumn get code => text().unique()();
  TextColumn get name => text()();
  TextColumn get address => text().withDefault(const Constant(''))();
  TextColumn get city => text().withDefault(const Constant(''))();
  TextColumn get phone => text().withDefault(const Constant(''))();
  IntColumn get managerId => integer().nullable()();
  BoolColumn get allowNegativeStock => boolean().withDefault(const Constant(false))();
  BoolColumn get isActive => boolean().withDefault(const Constant(true))();
  DateTimeColumn get updatedAt => dateTime().withDefault(currentDateAndTime)();
  BoolColumn get synced => boolean().withDefault(const Constant(true))();

  @override
  Set<Column> get primaryKey => {id};
}

// ─── Location ───

class Locations extends Table {
  IntColumn get id => integer()();
  IntColumn get warehouseId => integer().references(Warehouses, #id)();
  TextColumn get code => text()();
  TextColumn get name => text()();
  IntColumn get parentId => integer().nullable().references(Locations, #id)();
  TextColumn get locationType => text().withDefault(const Constant('BIN'))();
  BoolColumn get isPickable => boolean().withDefault(const Constant(true))();
  BoolColumn get isActive => boolean().withDefault(const Constant(true))();
  DateTimeColumn get updatedAt => dateTime().withDefault(currentDateAndTime)();
  BoolColumn get synced => boolean().withDefault(const Constant(true))();

  @override
  Set<Column> get primaryKey => {id};
}
