import 'dart:convert';

import 'package:drift/drift.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:uuid/uuid.dart';

import '../database/app_database.dart';

const _uuid = Uuid();

class POSRepository {
  final AppDatabase _db;

  POSRepository(this._db);

  // ─── Registers ───

  Stream<List<PosRegister>> watchRegisters() {
    return (_db.select(_db.posRegisters)
          ..where((t) => t.isActive.equals(true)))
        .watch();
  }

  // ─── Shifts ───

  Future<PosShift?> getOpenShift(int registerId, int userId) {
    return (_db.select(_db.posShifts)
          ..where((t) =>
              t.registerId.equals(registerId) &
              t.userId.equals(userId) &
              t.status.equals('OPEN')))
        .getSingleOrNull();
  }

  Future<int> openShift({
    required int registerId,
    required int userId,
    required double openingBalance,
  }) async {
    final localId = _uuid.v4();
    final id = await _db.into(_db.posShifts).insert(
          PosShiftsCompanion.insert(
            localId: Value(localId),
            registerId: registerId,
            userId: userId,
            openingBalance: Value(openingBalance),
            status: const Value('OPEN'),
            synced: const Value(false),
          ),
        );

    // Queue for sync
    await _db.queueChange(
      tableName: 'pos_shifts',
      localId: localId,
      operation: 'CREATE',
      payload: jsonEncode({
        'local_id': localId,
        'register': registerId,
        'user': userId,
        'opening_balance': openingBalance,
      }),
    );

    return id;
  }

  Future<void> closeShift(int shiftId, double closingBalance) async {
    final shift = await (_db.select(_db.posShifts)..where((t) => t.id.equals(shiftId))).getSingle();

    await (_db.update(_db.posShifts)..where((t) => t.id.equals(shiftId))).write(
      PosShiftsCompanion(
        closingBalance: Value(closingBalance),
        closedAt: Value(DateTime.now()),
        status: const Value('CLOSED'),
        synced: const Value(false),
      ),
    );

    await _db.queueChange(
      tableName: 'pos_shifts',
      recordId: shift.serverId,
      localId: shift.localId,
      operation: 'UPDATE',
      payload: jsonEncode({
        'local_id': shift.localId,
        'server_id': shift.serverId,
        'closing_balance': closingBalance,
        'status': 'CLOSED',
      }),
    );
  }

  // ─── Sales ───

  Stream<List<PosSale>> watchTodaySales() {
    final today = DateTime.now();
    final start = DateTime(today.year, today.month, today.day);
    return (_db.select(_db.posSales)
          ..where((t) => t.createdAt.isBiggerOrEqualValue(start))
          ..orderBy([(t) => OrderingTerm.desc(t.createdAt)]))
        .watch();
  }

  /// Create a complete POS sale with lines and payments — works fully offline
  Future<int> createSale({
    required int warehouseId,
    required int locationId,
    required int createdById,
    int? shiftId,
    int? customerId,
    required double subtotal,
    required double discountAmount,
    required double taxAmount,
    required double total,
    required double amountPaid,
    required double changeAmount,
    required List<Map<String, dynamic>> lines,
    required List<Map<String, dynamic>> payments,
    String notes = '',
  }) async {
    final localId = _uuid.v4();

    return await _db.transaction(() async {
      // 1. Create sale header
      final saleId = await _db.into(_db.posSales).insert(
            PosSalesCompanion.insert(
              localId: Value(localId),
              shiftId: Value(shiftId),
              customerId: Value(customerId),
              warehouseId: warehouseId,
              locationId: Value(locationId),
              subtotal: Value(subtotal),
              discountAmount: Value(discountAmount),
              taxAmount: Value(taxAmount),
              total: Value(total),
              amountPaid: Value(amountPaid),
              changeAmount: Value(changeAmount),
              status: const Value('COMPLETED'),
              notes: Value(notes),
              createdById: createdById,
              synced: const Value(false),
            ),
          );

      // 2. Create sale lines
      for (final line in lines) {
        await _db.into(_db.posSaleLines).insert(
              PosSaleLinesCompanion.insert(
                saleId: saleId,
                itemId: line['item_id'],
                unitId: line['unit_id'],
                locationId: Value(line['location_id']),
                qty: line['qty'],
                unitPrice: line['unit_price'],
                discountAmount: Value(line['discount_amount'] ?? 0.0),
                lineTotal: line['line_total'],
              ),
            );

        // 3. Deduct local stock balance
        final existing = await (_db.select(_db.stockBalances)
              ..where((t) =>
                  t.itemId.equals(line['item_id'] as int) &
                  t.locationId.equals(locationId)))
            .getSingleOrNull();

        if (existing != null) {
          await (_db.update(_db.stockBalances)
                ..where((t) => t.id.equals(existing.id)))
              .write(StockBalancesCompanion(
                qtyOnHand: Value(existing.qtyOnHand - (line['qty'] as double)),
                updatedAt: Value(DateTime.now()),
                synced: const Value(false),
              ));
        }
      }

      // 4. Create payments
      for (final payment in payments) {
        await _db.into(_db.posPayments).insert(
              PosPaymentsCompanion.insert(
                saleId: saleId,
                paymentMethod: payment['method'],
                amount: payment['amount'],
                referenceNumber: Value(payment['reference'] ?? ''),
              ),
            );
      }

      // 5. Queue for sync
      await _db.queueChange(
        tableName: 'pos_sales',
        localId: localId,
        operation: 'CREATE',
        payload: jsonEncode({
          'local_id': localId,
          'warehouse': warehouseId,
          'location': locationId,
          'shift': shiftId,
          'customer': customerId,
          'subtotal': subtotal,
          'discount_amount': discountAmount,
          'tax_amount': taxAmount,
          'total': total,
          'amount_paid': amountPaid,
          'change_amount': changeAmount,
          'notes': notes,
          'lines': lines,
          'payments': payments,
        }),
      );

      return saleId;
    });
  }

  // ─── Sale details ───

  Future<List<PosSaleLine>> getSaleLines(int saleId) {
    return (_db.select(_db.posSaleLines)..where((t) => t.saleId.equals(saleId))).get();
  }

  Future<List<PosPayment>> getSalePayments(int saleId) {
    return (_db.select(_db.posPayments)..where((t) => t.saleId.equals(saleId))).get();
  }
}

final posRepositoryProvider = Provider<POSRepository>((ref) {
  return POSRepository(ref.watch(databaseProvider));
});
