import 'package:drift/drift.dart';

// ─── Category ───

class Categories extends Table {
  IntColumn get id => integer()();
  TextColumn get code => text().unique()();
  TextColumn get name => text()();
  IntColumn get parentId => integer().nullable().references(Categories, #id)();
  TextColumn get description => text().withDefault(const Constant(''))();
  BoolColumn get isActive => boolean().withDefault(const Constant(true))();
  DateTimeColumn get updatedAt => dateTime().withDefault(currentDateAndTime)();
  BoolColumn get synced => boolean().withDefault(const Constant(true))();

  @override
  Set<Column> get primaryKey => {id};
}

// ─── Unit ───

class Units extends Table {
  IntColumn get id => integer()();
  TextColumn get name => text().unique()();
  TextColumn get abbreviation => text().unique()();
  TextColumn get category => text().withDefault(const Constant('quantity'))();
  BoolColumn get isActive => boolean().withDefault(const Constant(true))();
  DateTimeColumn get updatedAt => dateTime().withDefault(currentDateAndTime)();
  BoolColumn get synced => boolean().withDefault(const Constant(true))();

  @override
  Set<Column> get primaryKey => {id};
}

// ─── Unit Conversion ───

class UnitConversions extends Table {
  IntColumn get id => integer()();
  IntColumn get fromUnitId => integer().references(Units, #id)();
  IntColumn get toUnitId => integer().references(Units, #id)();
  RealColumn get factor => real()();
  RealColumn get conversionPrice => real().nullable()();
  IntColumn get itemId => integer().nullable()();
  BoolColumn get isActive => boolean().withDefault(const Constant(true))();
  DateTimeColumn get updatedAt => dateTime().withDefault(currentDateAndTime)();
  BoolColumn get synced => boolean().withDefault(const Constant(true))();

  @override
  Set<Column> get primaryKey => {id};
}

// ─── Item ───

class Items extends Table {
  IntColumn get id => integer()();
  TextColumn get code => text().unique()();
  TextColumn get name => text()();
  TextColumn get itemType => text().withDefault(const Constant('RAW'))();
  IntColumn get categoryId => integer().references(Categories, #id)();
  IntColumn get defaultUnitId => integer().references(Units, #id)();
  IntColumn get sellingUnitId => integer().nullable().references(Units, #id)();
  TextColumn get description => text().withDefault(const Constant(''))();
  TextColumn get barcode => text().withDefault(const Constant(''))();
  RealColumn get minimumStock => real().withDefault(const Constant(0))();
  RealColumn get maximumStock => real().withDefault(const Constant(0))();
  RealColumn get reorderPoint => real().withDefault(const Constant(0))();
  RealColumn get costPrice => real().withDefault(const Constant(0))();
  RealColumn get sellingPrice => real().withDefault(const Constant(0))();
  TextColumn get imagePath => text().nullable()();
  BoolColumn get isActive => boolean().withDefault(const Constant(true))();
  DateTimeColumn get updatedAt => dateTime().withDefault(currentDateAndTime)();
  BoolColumn get synced => boolean().withDefault(const Constant(true))();

  @override
  Set<Column> get primaryKey => {id};
}

// ─── Material Spec ───

class MaterialSpecs extends Table {
  IntColumn get id => integer()();
  IntColumn get itemId => integer().unique().references(Items, #id)();
  RealColumn get thickness => real().nullable()();
  RealColumn get length => real().nullable()();
  RealColumn get width => real().nullable()();
  TextColumn get color => text().withDefault(const Constant(''))();
  TextColumn get alloy => text().withDefault(const Constant(''))();
  TextColumn get grade => text().withDefault(const Constant(''))();
  DateTimeColumn get updatedAt => dateTime().withDefault(currentDateAndTime)();
  BoolColumn get synced => boolean().withDefault(const Constant(true))();

  @override
  Set<Column> get primaryKey => {id};
}

// ─── Product Spec ───

class ProductSpecs extends Table {
  IntColumn get id => integer()();
  IntColumn get itemId => integer().unique().references(Items, #id)();
  TextColumn get modelName => text().withDefault(const Constant(''))();
  TextColumn get variant => text().withDefault(const Constant(''))();
  TextColumn get dimensions => text().withDefault(const Constant(''))();
  RealColumn get weight => real().nullable()();
  DateTimeColumn get updatedAt => dateTime().withDefault(currentDateAndTime)();
  BoolColumn get synced => boolean().withDefault(const Constant(true))();

  @override
  Set<Column> get primaryKey => {id};
}
