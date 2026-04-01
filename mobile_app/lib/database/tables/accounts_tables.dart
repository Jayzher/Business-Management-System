import 'package:drift/drift.dart';

// ─── App User (mirrors accounts.User) ───

class AppUsers extends Table {
  IntColumn get id => integer()();
  TextColumn get username => text().unique()();
  TextColumn get email => text().withDefault(const Constant(''))();
  TextColumn get firstName => text().withDefault(const Constant(''))();
  TextColumn get lastName => text().withDefault(const Constant(''))();
  TextColumn get phone => text().withDefault(const Constant(''))();
  BoolColumn get isActive => boolean().withDefault(const Constant(true))();
  DateTimeColumn get updatedAt => dateTime().withDefault(currentDateAndTime)();
  BoolColumn get synced => boolean().withDefault(const Constant(true))();

  @override
  Set<Column> get primaryKey => {id};
}

// ─── Role ───

class Roles extends Table {
  IntColumn get id => integer()();
  TextColumn get name => text().unique()();
  TextColumn get description => text().withDefault(const Constant(''))();
  DateTimeColumn get updatedAt => dateTime().withDefault(currentDateAndTime)();

  @override
  Set<Column> get primaryKey => {id};
}

// ─── User Role ───

class UserRoles extends Table {
  IntColumn get id => integer()();
  IntColumn get userId => integer().references(AppUsers, #id)();
  IntColumn get roleId => integer().references(Roles, #id)();

  @override
  Set<Column> get primaryKey => {id};
}

// ─── Warehouse Permission ───

class WarehousePermissions extends Table {
  IntColumn get id => integer()();
  IntColumn get userId => integer().references(AppUsers, #id)();
  IntColumn get warehouseId => integer()();
  BoolColumn get canView => boolean().withDefault(const Constant(true))();
  BoolColumn get canReceive => boolean().withDefault(const Constant(false))();
  BoolColumn get canDeliver => boolean().withDefault(const Constant(false))();
  BoolColumn get canTransfer => boolean().withDefault(const Constant(false))();
  BoolColumn get canAdjust => boolean().withDefault(const Constant(false))();
  BoolColumn get canManage => boolean().withDefault(const Constant(false))();

  @override
  Set<Column> get primaryKey => {id};
}
