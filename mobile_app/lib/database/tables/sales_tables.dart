import 'package:drift/drift.dart';

import 'catalog_tables.dart';
import 'warehouses_tables.dart';
import 'partners_tables.dart';
import 'accounts_tables.dart';

// ─── Sales Order ───

class SalesOrders extends Table {
  IntColumn get id => integer().autoIncrement()();
  TextColumn get localId => text().nullable()();
  IntColumn get serverId => integer().nullable()();
  TextColumn get documentNumber => text().withDefault(const Constant(''))();
  TextColumn get status => text().withDefault(const Constant('DRAFT'))();
  IntColumn get customerId => integer().nullable().references(Customers, #id)();
  IntColumn get warehouseId => integer().references(Warehouses, #id)();
  IntColumn get priceListId => integer().nullable()();
  RealColumn get subtotal => real().withDefault(const Constant(0))();
  RealColumn get discountAmount => real().withDefault(const Constant(0))();
  RealColumn get taxAmount => real().withDefault(const Constant(0))();
  RealColumn get total => real().withDefault(const Constant(0))();
  TextColumn get notes => text().withDefault(const Constant(''))();
  IntColumn get createdById => integer().references(AppUsers, #id)();
  DateTimeColumn get createdAt => dateTime().withDefault(currentDateAndTime)();
  BoolColumn get synced => boolean().withDefault(const Constant(false))();
}

// ─── Sales Order Line ───

class SalesOrderLines extends Table {
  IntColumn get id => integer().autoIncrement()();
  IntColumn get orderId => integer().references(SalesOrders, #id)();
  IntColumn get itemId => integer().references(Items, #id)();
  IntColumn get unitId => integer().references(Units, #id)();
  RealColumn get qty => real()();
  RealColumn get unitPrice => real()();
  RealColumn get discountAmount => real().withDefault(const Constant(0))();
  RealColumn get lineTotal => real()();
  TextColumn get notes => text().withDefault(const Constant(''))();
}

// ─── Delivery Note ───

class DeliveryNotes extends Table {
  IntColumn get id => integer().autoIncrement()();
  TextColumn get localId => text().nullable()();
  IntColumn get serverId => integer().nullable()();
  TextColumn get documentNumber => text().withDefault(const Constant(''))();
  TextColumn get status => text().withDefault(const Constant('DRAFT'))();
  IntColumn get salesOrderId => integer().nullable().references(SalesOrders, #id)();
  IntColumn get customerId => integer().nullable().references(Customers, #id)();
  IntColumn get warehouseId => integer().references(Warehouses, #id)();
  TextColumn get notes => text().withDefault(const Constant(''))();
  IntColumn get createdById => integer().references(AppUsers, #id)();
  DateTimeColumn get createdAt => dateTime().withDefault(currentDateAndTime)();
  BoolColumn get synced => boolean().withDefault(const Constant(false))();
}

class DeliveryLines extends Table {
  IntColumn get id => integer().autoIncrement()();
  IntColumn get deliveryNoteId => integer().references(DeliveryNotes, #id)();
  IntColumn get itemId => integer().references(Items, #id)();
  IntColumn get locationId => integer().nullable().references(Locations, #id)();
  IntColumn get unitId => integer().references(Units, #id)();
  RealColumn get qty => real()();
  TextColumn get batchNumber => text().withDefault(const Constant(''))();
  TextColumn get notes => text().withDefault(const Constant(''))();
}
