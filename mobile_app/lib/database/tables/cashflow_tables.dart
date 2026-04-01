import 'package:drift/drift.dart';

import 'accounts_tables.dart';

// ─── CashFlow Transaction ───

class CashFlowTransactions extends Table {
  IntColumn get id => integer().autoIncrement()();
  TextColumn get localId => text().nullable()();
  IntColumn get serverId => integer().nullable()();
  TextColumn get category => text()(); // PROCUREMENT, SALES, SUPPLIES, EXPENSES, CAPITAL, OTHER
  TextColumn get flowType => text()(); // CASH_IN, CASH_OUT
  RealColumn get amount => real()();
  TextColumn get paymentMethod => text().withDefault(const Constant('CASH'))();
  TextColumn get referenceNumber => text().withDefault(const Constant(''))();
  TextColumn get referenceType => text().withDefault(const Constant(''))();
  IntColumn get referenceId => integer().nullable()();
  TextColumn get description => text().withDefault(const Constant(''))();
  TextColumn get status => text().withDefault(const Constant('PENDING'))();
  DateTimeColumn get transactionDate => dateTime().withDefault(currentDateAndTime)();
  IntColumn get createdById => integer().references(AppUsers, #id)();
  DateTimeColumn get createdAt => dateTime().withDefault(currentDateAndTime)();
  BoolColumn get synced => boolean().withDefault(const Constant(false))();
}
