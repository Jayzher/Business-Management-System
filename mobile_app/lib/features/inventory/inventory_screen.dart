import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../database/app_database.dart';
import '../../repositories/inventory_repository.dart';
import '../../sync/sync_engine.dart';
import '../../widgets/sync_status_widget.dart';
import '../../widgets/empty_state.dart';
import '../../utils/responsive.dart';

class InventoryScreen extends ConsumerWidget {
  const InventoryScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final warehouses = ref.watch(
      StreamProvider((ref) => ref.watch(inventoryRepositoryProvider).watchWarehouses()),
    );
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Inventory'),
        actions: const [SyncStatusWidget(), SizedBox(width: 8)],
      ),
      body: RefreshIndicator(
        onRefresh: () async {
          await ref.read(syncEngineProvider).syncIfNeeded();
        },
        child: ResponsiveCenter(
          child: ListView(
          padding: Responsive.bodyPadding(context),
          children: [
            // Quick actions grid
            Row(
              children: [
                Expanded(
                  child: _ActionCard(
                    icon: Icons.inventory_outlined,
                    label: 'Stock\nBalances',
                    color: Colors.blue,
                    onTap: () {
                      HapticFeedback.lightImpact();
                      context.go('/inventory/balances');
                    },
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: _ActionCard(
                    icon: Icons.swap_horiz_outlined,
                    label: 'Stock\nMovements',
                    color: Colors.orange,
                    onTap: () {
                      HapticFeedback.lightImpact();
                      context.go('/inventory/moves');
                    },
                  ),
                ),
              ],
            ),

            const SizedBox(height: 24),
            Text(
              'Warehouses',
              style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w600),
            ),
            const SizedBox(height: 8),

            warehouses.when(
              data: (list) {
                if (list.isEmpty) {
                  return const EmptyState(
                    icon: Icons.warehouse_outlined,
                    title: 'No Warehouses',
                    subtitle: 'Warehouses will appear after syncing with the server',
                  );
                }
                return Column(
                  children: list.map((w) => Card(
                    margin: const EdgeInsets.only(bottom: 8),
                    child: ListTile(
                      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
                      leading: Container(
                        width: 44,
                        height: 44,
                        decoration: BoxDecoration(
                          color: Colors.orange.withAlpha(25),
                          borderRadius: BorderRadius.circular(12),
                        ),
                        child: const Icon(Icons.warehouse_outlined, color: Colors.orange, size: 24),
                      ),
                      title: Text(w.name, style: theme.textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w600)),
                      subtitle: Text(
                        '${w.code} • ${w.city}',
                        style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.outline),
                      ),
                      trailing: const Icon(Icons.chevron_right, size: 20),
                      onTap: () {
                        HapticFeedback.selectionClick();
                        context.go('/inventory/balances');
                      },
                    ),
                  )).toList(),
                );
              },
              loading: () => const Center(
                child: Padding(
                  padding: EdgeInsets.all(32),
                  child: CircularProgressIndicator(),
                ),
              ),
              error: (e, _) => Center(child: Text('Error: $e')),
            ),
          ],
        ),
        ),
      ),
    );
  }
}

class _ActionCard extends StatelessWidget {
  final IconData icon;
  final String label;
  final Color color;
  final VoidCallback onTap;

  const _ActionCard({
    required this.icon,
    required this.label,
    required this.color,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            children: [
              Container(
                width: 44,
                height: 44,
                decoration: BoxDecoration(
                  color: color.withAlpha(25),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Icon(icon, size: 24, color: color),
              ),
              const SizedBox(height: 10),
              Text(
                label,
                textAlign: TextAlign.center,
                style: theme.textTheme.labelMedium?.copyWith(fontWeight: FontWeight.w600),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
