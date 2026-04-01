import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../database/app_database.dart';
import '../../repositories/inventory_repository.dart';
import '../../widgets/empty_state.dart';
import '../../utils/responsive.dart';

class StockMovesScreen extends ConsumerWidget {
  const StockMovesScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final moves = ref.watch(_recentMovesProvider);
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(title: const Text('Stock Movements')),
      body: ResponsiveCenter(
        child: moves.when(
        data: (list) {
          if (list.isEmpty) {
            return const EmptyState(
              icon: Icons.swap_horiz,
              title: 'No Stock Movements',
              subtitle: 'Stock movements from POS sales, transfers, and adjustments will appear here',
            );
          }
          return ListView.builder(
            padding: const EdgeInsets.symmetric(vertical: 8),
            itemCount: list.length,
            itemBuilder: (context, index) {
              final m = list[index];
              final isPositive = m.qty > 0;
              return Card(
                margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
                child: ListTile(
                  leading: Container(
                    width: 40,
                    height: 40,
                    decoration: BoxDecoration(
                      color: isPositive
                          ? Colors.green.withAlpha(30)
                          : Colors.red.withAlpha(30),
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: Icon(
                      isPositive ? Icons.add_circle_outline : Icons.remove_circle_outline,
                      color: isPositive ? Colors.green : Colors.red,
                      size: 22,
                    ),
                  ),
                  title: Text(
                    'Item #${m.itemId}',
                    style: theme.textTheme.bodyMedium?.copyWith(fontWeight: FontWeight.w600),
                  ),
                  subtitle: Text(
                    '${m.moveType} • Location #${m.locationId}',
                    style: theme.textTheme.bodySmall,
                  ),
                  trailing: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    crossAxisAlignment: CrossAxisAlignment.end,
                    children: [
                      Text(
                        '${isPositive ? "+" : ""}${m.qty.toStringAsFixed(2)}',
                        style: theme.textTheme.titleSmall?.copyWith(
                          fontWeight: FontWeight.bold,
                          color: isPositive ? Colors.green : Colors.red,
                        ),
                      ),
                      Text(
                        _formatTime(m.createdAt),
                        style: theme.textTheme.labelSmall?.copyWith(
                          color: theme.colorScheme.outline,
                        ),
                      ),
                    ],
                  ),
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

  String _formatTime(DateTime time) {
    return '${time.hour.toString().padLeft(2, '0')}:${time.minute.toString().padLeft(2, '0')}';
  }
}

final _recentMovesProvider = StreamProvider<List<StockMove>>((ref) {
  return ref.watch(inventoryRepositoryProvider).watchRecentMoves();
});
