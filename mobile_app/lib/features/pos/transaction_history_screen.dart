import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../database/app_database.dart';
import '../../repositories/pos_repository.dart';
import '../../widgets/empty_state.dart';
import '../../utils/responsive.dart';

class TransactionHistoryScreen extends ConsumerWidget {
  const TransactionHistoryScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final sales = ref.watch(_todaySalesProvider);
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Transactions'),
      ),
      body: ResponsiveCenter(
        child: sales.when(
        data: (list) {
          if (list.isEmpty) {
            return const EmptyState(
              icon: Icons.receipt_long_outlined,
              title: 'No Transactions Yet',
              subtitle: 'POS sales will appear here',
            );
          }
          return ListView.builder(
            padding: const EdgeInsets.symmetric(vertical: 8),
            itemCount: list.length,
            itemBuilder: (context, index) {
              final sale = list[index];
              final time = sale.createdAt;
              return Card(
                margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
                child: ListTile(
                  leading: Container(
                    width: 44,
                    height: 44,
                    decoration: BoxDecoration(
                      color: sale.synced
                          ? Colors.green.withAlpha(30)
                          : Colors.orange.withAlpha(30),
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: Icon(
                      sale.synced ? Icons.cloud_done : Icons.cloud_upload_outlined,
                      color: sale.synced ? Colors.green : Colors.orange,
                      size: 22,
                    ),
                  ),
                  title: Text(
                    '₱${sale.total.toStringAsFixed(2)}',
                    style: theme.textTheme.titleMedium?.copyWith(
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  subtitle: Text(
                    '${_formatTime(time)} • ${sale.status}',
                    style: theme.textTheme.bodySmall,
                  ),
                  trailing: Text(
                    '#${(sale.localId ?? '').substring(0, 6).toUpperCase()}',
                    style: theme.textTheme.labelSmall?.copyWith(
                      fontFamily: 'monospace',
                      color: theme.colorScheme.outline,
                    ),
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

final _todaySalesProvider = StreamProvider<List<PosSale>>((ref) {
  return ref.watch(posRepositoryProvider).watchTodaySales();
});
