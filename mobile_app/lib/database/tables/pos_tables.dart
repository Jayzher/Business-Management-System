import 'package:drift/drift.dart';

import 'catalog_tables.dart';
import 'warehouses_tables.dart';
import 'partners_tables.dart';
import 'accounts_tables.dart';

// ─── POS Register ───

class PosRegisters extends Table {
  IntColumn get id => integer()();
  TextColumn get name => text()();
  IntColumn get warehouseId => integer().references(Warehouses, #id)();
  IntColumn get defaultLocationId => integer().nullable().references(Locations, #id)();
  IntColumn get priceListId => integer().nullable()();
  BoolColumn get isActive => boolean().withDefault(const Constant(true))();
  DateTimeColumn get updatedAt => dateTime().withDefault(currentDateAndTime)();
  BoolColumn get synced => boolean().withDefault(const Constant(true))();

  @override
  Set<Column> get primaryKey => {id};
}

// ─── POS Shift ───

class PosShifts extends Table {
  IntColumn get id => integer().autoIncrement()();
  TextColumn get localId => text().nullable()();
  IntColumn get serverId => integer().nullable()();
  IntColumn get registerId => integer().references(PosRegisters, #id)();
  IntColumn get userId => integer().references(AppUsers, #id)();
  RealColumn get openingBalance => real().withDefault(const Constant(0))();
  RealColumn get closingBalance => real().nullable()();
  RealColumn get expectedBalance => real().nullable()();
  RealColumn get difference => real().nullable()();
  DateTimeColumn get openedAt => dateTime().withDefault(currentDateAndTime)();
  DateTimeColumn get closedAt => dateTime().nullable()();
  TextColumn get status => text().withDefault(const Constant('OPEN'))();
  TextColumn get notes => text().withDefault(const Constant(''))();
  BoolColumn get synced => boolean().withDefault(const Constant(false))();
}

// ─── POS Sale ───

class PosSales extends Table {
  IntColumn get id => integer().autoIncrement()();
  TextColumn get localId => text().nullable()(); // UUID for offline-created
  IntColumn get serverId => integer().nullable()();
  TextColumn get receiptNumber => text().withDefault(const Constant(''))();
  IntColumn get shiftId => integer().nullable()();
  IntColumn get customerId => integer().nullable().references(Customers, #id)();
  IntColumn get warehouseId => integer().references(Warehouses, #id)();
  IntColumn get locationId => integer().nullable().references(Locations, #id)();
  RealColumn get subtotal => real().withDefault(const Constant(0))();
  RealColumn get discountAmount => real().withDefault(const Constant(0))();
  RealColumn get taxAmount => real().withDefault(const Constant(0))();
  RealColumn get total => real().withDefault(const Constant(0))();
  RealColumn get amountPaid => real().withDefault(const Constant(0))();
  RealColumn get changeAmount => real().withDefault(const Constant(0))();
  TextColumn get status => text().withDefault(const Constant('COMPLETED'))();
  TextColumn get notes => text().withDefault(const Constant(''))();
  IntColumn get createdById => integer().references(AppUsers, #id)();
  DateTimeColumn get createdAt => dateTime().withDefault(currentDateAndTime)();
  BoolColumn get synced => boolean().withDefault(const Constant(false))();
}

// ─── POS Sale Line ───

class PosSaleLines extends Table {
  IntColumn get id => integer().autoIncrement()();
  IntColumn get saleId => integer().references(PosSales, #id)();
  IntColumn get itemId => integer().references(Items, #id)();
  IntColumn get unitId => integer().references(Units, #id)();
  IntColumn get locationId => integer().nullable().references(Locations, #id)();
  RealColumn get qty => real()();
  RealColumn get unitPrice => real()();
  RealColumn get discountAmount => real().withDefault(const Constant(0))();
  RealColumn get lineTotal => real()();
  TextColumn get notes => text().withDefault(const Constant(''))();
}

// ─── POS Payment ───

class PosPayments extends Table {
  IntColumn get id => integer().autoIncrement()();
  IntColumn get saleId => integer().references(PosSales, #id)();
  TextColumn get paymentMethod => text()(); // CASH, GCASH, CARD, etc.
  RealColumn get amount => real()();
  TextColumn get referenceNumber => text().withDefault(const Constant(''))();
}

// ─── POS Cash Entry ───

class PosCashEntries extends Table {
  IntColumn get id => integer().autoIncrement()();
  TextColumn get localId => text().nullable()();
  IntColumn get serverId => integer().nullable()();
  IntColumn get shiftId => integer().nullable()();
  TextColumn get entryType => text()(); // CASH_IN, CASH_OUT
  RealColumn get amount => real()();
  TextColumn get reason => text().withDefault(const Constant(''))();
  IntColumn get createdById => integer().references(AppUsers, #id)();
  DateTimeColumn get createdAt => dateTime().withDefault(currentDateAndTime)();
  BoolColumn get synced => boolean().withDefault(const Constant(false))();
}
