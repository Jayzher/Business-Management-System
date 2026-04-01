import 'package:drift/drift.dart';

// ─── Sync Metadata ───

class SyncMeta extends Table {
  TextColumn get tableName => text().named('table_name')();
  DateTimeColumn get lastPulledAt => dateTime().nullable()();
  DateTimeColumn get lastPushedAt => dateTime().nullable()();

  @override
  Set<Column> get primaryKey => {tableName};
}

class SyncQueue extends Table {
  IntColumn get id => integer().autoIncrement()();
  TextColumn get tableName => text().named('table_name')();
  IntColumn get recordId => integer().nullable()();
  TextColumn get localId => text().nullable()(); // UUID for offline-created
  TextColumn get operation => text()(); // CREATE, UPDATE, DELETE
  TextColumn get payload => text()(); // JSON data
  DateTimeColumn get createdAt => dateTime().withDefault(currentDateAndTime)();
  IntColumn get retryCount => integer().withDefault(const Constant(0))();
  TextColumn get errorMessage => text().nullable()();
}
