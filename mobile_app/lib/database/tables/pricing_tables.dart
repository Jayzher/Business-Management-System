import 'package:drift/drift.dart';

import 'catalog_tables.dart';
import 'warehouses_tables.dart';
import 'partners_tables.dart';
import 'accounts_tables.dart';

// ─── Price List ───

class PriceLists extends Table {
  IntColumn get id => integer()();
  TextColumn get name => text()();
  IntColumn get warehouseId => integer().nullable().references(Warehouses, #id)();
  TextColumn get currency => text().withDefault(const Constant('PHP'))();
  BoolColumn get isDefault => boolean().withDefault(const Constant(false))();
  BoolColumn get isActive => boolean().withDefault(const Constant(true))();
  DateTimeColumn get updatedAt => dateTime().withDefault(currentDateAndTime)();
  BoolColumn get synced => boolean().withDefault(const Constant(true))();

  @override
  Set<Column> get primaryKey => {id};
}

// ─── Price List Item ───

class PriceListItems extends Table {
  IntColumn get id => integer()();
  IntColumn get priceListId => integer().references(PriceLists, #id)();
  IntColumn get itemId => integer().references(Items, #id)();
  IntColumn get unitId => integer().references(Units, #id)();
  RealColumn get price => real()();
  RealColumn get minQty => real().withDefault(const Constant(1))();
  DateTimeColumn get startDate => dateTime().nullable()();
  DateTimeColumn get endDate => dateTime().nullable()();
  DateTimeColumn get updatedAt => dateTime().withDefault(currentDateAndTime)();
  BoolColumn get synced => boolean().withDefault(const Constant(true))();

  @override
  Set<Column> get primaryKey => {id};
}

// ─── Customer Price Catalog ───

class CustomerPriceCatalogs extends Table {
  IntColumn get id => integer()();
  IntColumn get customerId => integer().references(Customers, #id)();
  TextColumn get name => text()();
  DateTimeColumn get startDate => dateTime().nullable()();
  DateTimeColumn get endDate => dateTime().nullable()();
  TextColumn get notes => text().withDefault(const Constant(''))();
  BoolColumn get isActive => boolean().withDefault(const Constant(true))();
  DateTimeColumn get updatedAt => dateTime().withDefault(currentDateAndTime)();
  BoolColumn get synced => boolean().withDefault(const Constant(true))();

  @override
  Set<Column> get primaryKey => {id};
}

// ─── Customer Price Catalog Item ───

class CustomerPriceCatalogItems extends Table {
  IntColumn get id => integer()();
  IntColumn get catalogId => integer().references(CustomerPriceCatalogs, #id)();
  IntColumn get itemId => integer().references(Items, #id)();
  IntColumn get unitId => integer().references(Units, #id)();
  RealColumn get price => real()();
  TextColumn get notes => text().withDefault(const Constant(''))();

  @override
  Set<Column> get primaryKey => {id};
}

// ─── Discount Rule ───

class DiscountRules extends Table {
  IntColumn get id => integer()();
  TextColumn get name => text()();
  TextColumn get discountType => text()(); // PERCENT, FIXED
  RealColumn get value => real()();
  TextColumn get scope => text().withDefault(const Constant('ORDER'))(); // ITEM, ORDER
  BoolColumn get isActive => boolean().withDefault(const Constant(true))();
  DateTimeColumn get updatedAt => dateTime().withDefault(currentDateAndTime)();
  BoolColumn get synced => boolean().withDefault(const Constant(true))();

  @override
  Set<Column> get primaryKey => {id};
}
