import 'package:drift/drift.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../database/app_database.dart';

class PartnersRepository {
  final AppDatabase _db;

  PartnersRepository(this._db);

  // ─── Customers ───

  Stream<List<Customer>> watchCustomers({String? search}) {
    final query = _db.select(_db.customers)
      ..where((t) => t.isActive.equals(true));
    if (search != null && search.isNotEmpty) {
      query.where((t) => t.name.contains(search) | t.code.contains(search));
    }
    query.orderBy([(t) => OrderingTerm.asc(t.name)]);
    return query.watch();
  }

  Future<Customer?> getCustomerById(int id) {
    return (_db.select(_db.customers)..where((t) => t.id.equals(id))).getSingleOrNull();
  }

  // ─── Suppliers ───

  Stream<List<Supplier>> watchSuppliers({String? search}) {
    final query = _db.select(_db.suppliers)
      ..where((t) => t.isActive.equals(true));
    if (search != null && search.isNotEmpty) {
      query.where((t) => t.name.contains(search) | t.code.contains(search));
    }
    query.orderBy([(t) => OrderingTerm.asc(t.name)]);
    return query.watch();
  }
}

final partnersRepositoryProvider = Provider<PartnersRepository>((ref) {
  return PartnersRepository(ref.watch(databaseProvider));
});
