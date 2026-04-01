import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../widgets/sync_status_widget.dart';
import '../../widgets/empty_state.dart';
import '../../utils/responsive.dart';

class SalesScreen extends ConsumerWidget {
  const SalesScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Sales Orders'),
        actions: const [SyncStatusWidget(), SizedBox(width: 8)],
      ),
      body: const ResponsiveCenter(
        child: EmptyState(
          icon: Icons.receipt_long_outlined,
          title: 'Sales Orders',
          subtitle: 'Create and manage sales orders offline.\nThis feature is coming soon.',
        ),
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () {
          showModalBottomSheet(
            context: context,
            isScrollControlled: true,
            useSafeArea: true,
            builder: (_) => const _CreateSalesOrderSheet(),
          );
        },
        icon: const Icon(Icons.add),
        label: const Text('New Order'),
      ),
    );
  }
}

class _CreateSalesOrderSheet extends StatefulWidget {
  const _CreateSalesOrderSheet();

  @override
  State<_CreateSalesOrderSheet> createState() => _CreateSalesOrderSheetState();
}

class _CreateSalesOrderSheetState extends State<_CreateSalesOrderSheet> {
  final _notesController = TextEditingController();

  @override
  void dispose() {
    _notesController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return DraggableScrollableSheet(
      initialChildSize: 0.8,
      maxChildSize: 0.95,
      minChildSize: 0.5,
      expand: false,
      builder: (context, scrollController) {
        return Column(
          children: [
            Container(
              margin: const EdgeInsets.only(top: 12),
              width: 40,
              height: 4,
              decoration: BoxDecoration(
                color: theme.colorScheme.outlineVariant,
                borderRadius: BorderRadius.circular(2),
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 16, 20, 0),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text('New Sales Order',
                      style: theme.textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.bold)),
                  IconButton(
                    icon: const Icon(Icons.close),
                    onPressed: () => Navigator.of(context).pop(),
                  ),
                ],
              ),
            ),
            Expanded(
              child: ListView(
                controller: scrollController,
                padding: const EdgeInsets.all(20),
                children: [
                  // Customer selection
                  Text('Customer', style: theme.textTheme.labelLarge),
                  const SizedBox(height: 8),
                  Card(
                    child: ListTile(
                      leading: const Icon(Icons.person_add_outlined),
                      title: const Text('Select Customer'),
                      subtitle: const Text('Tap to choose a customer'),
                      trailing: const Icon(Icons.chevron_right),
                      onTap: () {
                        ScaffoldMessenger.of(context).showSnackBar(
                          const SnackBar(content: Text('Customer selection coming soon')),
                        );
                      },
                    ),
                  ),

                  const SizedBox(height: 20),

                  // Items
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text('Items', style: theme.textTheme.labelLarge),
                      FilledButton.tonalIcon(
                        onPressed: () {
                          ScaffoldMessenger.of(context).showSnackBar(
                            const SnackBar(content: Text('Item selection coming soon')),
                          );
                        },
                        icon: const Icon(Icons.add, size: 18),
                        label: const Text('Add Item'),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  Card(
                    child: Padding(
                      padding: const EdgeInsets.all(24),
                      child: Center(
                        child: Column(
                          children: [
                            Icon(Icons.shopping_bag_outlined,
                                size: 32, color: theme.colorScheme.outline),
                            const SizedBox(height: 8),
                            Text(
                              'No items added',
                              style: theme.textTheme.bodyMedium?.copyWith(
                                color: theme.colorScheme.outline,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),

                  const SizedBox(height: 20),

                  // Notes
                  Text('Notes', style: theme.textTheme.labelLarge),
                  const SizedBox(height: 8),
                  TextField(
                    controller: _notesController,
                    maxLines: 3,
                    decoration: InputDecoration(
                      hintText: 'Add notes to this order...',
                      border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
                    ),
                  ),
                ],
              ),
            ),

            // Bottom action
            Container(
              padding: const EdgeInsets.fromLTRB(20, 12, 20, 12),
              decoration: BoxDecoration(
                color: theme.colorScheme.surface,
                border: Border(
                  top: BorderSide(color: theme.colorScheme.outlineVariant),
                ),
              ),
              child: SafeArea(
                child: SizedBox(
                  width: double.infinity,
                  child: FilledButton(
                    onPressed: () {
                      ScaffoldMessenger.of(context).showSnackBar(
                        const SnackBar(content: Text('Sales order creation coming soon')),
                      );
                    },
                    child: const Text('Create Draft Order'),
                  ),
                ),
              ),
            ),
          ],
        );
      },
    );
  }
}
