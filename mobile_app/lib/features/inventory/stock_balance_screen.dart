import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../database/app_database.dart';
import '../../repositories/inventory_repository.dart';
import '../../widgets/empty_state.dart';
import '../../utils/responsive.dart';

final _balancesProvider = StreamProvider<List<StockBalance>>((ref) {
  return ref.watch(inventoryRepositoryProvider).watchBalances();
});

class StockBalanceScreen extends ConsumerWidget {
  const StockBalanceScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final balances = ref.watch(_balancesProvider);
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(title: const Text('Stock Balances')),
      body: ResponsiveCenter(
        child: balances.when(
        data: (list) {
          if (list.isEmpty) {
            return const EmptyState(
              icon: Icons.inventory_2_outlined,
              title: 'No Stock Data',
              subtitle: 'Stock balances will appear here after syncing',
            );
          }
          return ListView.separated(
            itemCount: list.length,
            padding: const EdgeInsets.symmetric(vertical: 8),
            separatorBuilder: (_, __) => const Divider(indent: 72, endIndent: 16),
            itemBuilder: (context, index) {
              final b = list[index];
              final available = b.qtyOnHand - b.qtyReserved;
              final isLow = available <= 0;

              return ListTile(
                contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 2),
                leading: Container(
                  width: 44,
                  height: 44,
                  decoration: BoxDecoration(
                    color: isLow
                        ? Colors.red.withAlpha(25)
                        : Colors.green.withAlpha(25),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Icon(
                    isLow ? Icons.warning_amber_outlined : Icons.check_circle_outline,
                    color: isLow ? Colors.red : Colors.green,
                    size: 22,
                  ),
                ),
                title: Text(
                  'Item #${b.itemId}',
                  style: theme.textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w600),
                ),
                subtitle: Row(
                  children: [
                    Text(
                      'Location #${b.locationId}',
                      style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.outline),
                    ),
                    if (b.qtyReserved > 0) ...[
                      const SizedBox(width: 8),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
                        decoration: BoxDecoration(
                          color: Colors.orange.withAlpha(25),
                          borderRadius: BorderRadius.circular(4),
                        ),
                        child: Text(
                          'Reserved: ${b.qtyReserved.toStringAsFixed(2)}',
                          style: const TextStyle(color: Colors.orange, fontSize: 10, fontWeight: FontWeight.w600),
                        ),
                      ),
                    ],
                  ],
                ),
                trailing: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    Text(
                      b.qtyOnHand.toStringAsFixed(2),
                      style: theme.textTheme.titleSmall?.copyWith(fontWeight: FontWeight.bold),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      'Avail: ${available.toStringAsFixed(2)}',
                      style: TextStyle(
                        color: available > 0 ? Colors.green : Colors.red,
                        fontSize: 11,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ],
                ),
              );
            },
          );
        },
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text('Error: $e')),
      ),
      ),
    );
  }
}
