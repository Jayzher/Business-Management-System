import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../database/app_database.dart';
import '../../repositories/catalog_repository.dart';
import '../../repositories/inventory_repository.dart';
import '../../utils/responsive.dart';

class ItemDetailScreen extends ConsumerWidget {
  final int itemId;

  const ItemDetailScreen({super.key, required this.itemId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final catalogRepo = ref.watch(catalogRepositoryProvider);
    final theme = Theme.of(context);

    return FutureBuilder<Item?>(
      future: catalogRepo.getItemById(itemId),
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return const Scaffold(body: Center(child: CircularProgressIndicator()));
        }
        if (!snapshot.hasData || snapshot.data == null) {
          return Scaffold(
            appBar: AppBar(),
            body: const Center(child: Text('Item not found')),
          );
        }

        final item = snapshot.data!;
        final typeColor = switch (item.itemType) {
          'RAW' => Colors.orange,
          'FINISHED' => Colors.blue,
          'SERVICE' => Colors.purple,
          _ => Colors.grey,
        };

        return Scaffold(
          appBar: AppBar(
            title: Text(item.name),
          ),
          body: ResponsiveCenter(
            child: ListView(
            padding: Responsive.bodyPadding(context),
            children: [
              // Header with type badge
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(20),
                  child: Column(
                    children: [
                      // Item icon with type indicator
                      Container(
                        width: 64,
                        height: 64,
                        decoration: BoxDecoration(
                          color: typeColor.withAlpha(25),
                          borderRadius: BorderRadius.circular(16),
                        ),
                        child: Center(
                          child: Text(
                            item.code.substring(0, item.code.length.clamp(0, 3)).toUpperCase(),
                            style: TextStyle(
                              fontWeight: FontWeight.bold,
                              color: typeColor,
                              fontSize: 20,
                            ),
                          ),
                        ),
                      ),
                      const SizedBox(height: 12),
                      Text(item.name, style: theme.textTheme.titleLarge, textAlign: TextAlign.center),
                      const SizedBox(height: 6),
                      Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Container(
                            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 3),
                            decoration: BoxDecoration(
                              color: typeColor.withAlpha(25),
                              borderRadius: BorderRadius.circular(12),
                            ),
                            child: Text(
                              item.itemType,
                              style: TextStyle(
                                color: typeColor,
                                fontWeight: FontWeight.w600,
                                fontSize: 12,
                              ),
                            ),
                          ),
                          const SizedBox(width: 8),
                          Text(
                            item.code,
                            style: theme.textTheme.bodyMedium?.copyWith(
                              fontFamily: 'monospace',
                              color: theme.colorScheme.outline,
                            ),
                          ),
                        ],
                      ),
                      if (item.barcode.isNotEmpty) ...[
                        const SizedBox(height: 4),
                        Row(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            Icon(Icons.qr_code, size: 14, color: theme.colorScheme.outline),
                            const SizedBox(width: 4),
                            Text(
                              item.barcode,
                              style: theme.textTheme.bodySmall?.copyWith(
                                color: theme.colorScheme.outline,
                              ),
                            ),
                          ],
                        ),
                      ],
                    ],
                  ),
                ),
              ),

              const SizedBox(height: 16),

              // Pricing card
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Icon(Icons.payments_outlined, size: 20, color: theme.colorScheme.primary),
                          const SizedBox(width: 8),
                          Text('Pricing', style: theme.textTheme.titleMedium),
                        ],
                      ),
                      const SizedBox(height: 12),
                      Row(
                        children: [
                          Expanded(
                            child: _PriceBox(
                              label: 'Cost Price',
                              value: '₱${item.costPrice.toStringAsFixed(2)}',
                              color: theme.colorScheme.outline,
                            ),
                          ),
                          const SizedBox(width: 12),
                          Expanded(
                            child: _PriceBox(
                              label: 'Selling Price',
                              value: '₱${item.sellingPrice.toStringAsFixed(2)}',
                              color: theme.colorScheme.primary,
                            ),
                          ),
                        ],
                      ),
                      if (item.sellingPrice > item.costPrice && item.costPrice > 0) ...[
                        const SizedBox(height: 8),
                        Row(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            Icon(Icons.trending_up, size: 16, color: Colors.green[600]),
                            const SizedBox(width: 4),
                            Text(
                              'Margin: ${((item.sellingPrice - item.costPrice) / item.costPrice * 100).toStringAsFixed(1)}%',
                              style: TextStyle(
                                color: Colors.green[600],
                                fontWeight: FontWeight.w600,
                                fontSize: 13,
                              ),
                            ),
                          ],
                        ),
                      ],
                    ],
                  ),
                ),
              ),

              const SizedBox(height: 16),

              // Stock levels card
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Icon(Icons.inventory_outlined, size: 20, color: theme.colorScheme.primary),
                          const SizedBox(width: 8),
                          Text('Stock Levels', style: theme.textTheme.titleMedium),
                        ],
                      ),
                      const SizedBox(height: 12),
                      _InfoRow('Minimum Stock', item.minimumStock.toStringAsFixed(2)),
                      _InfoRow('Maximum Stock', item.maximumStock.toStringAsFixed(2)),
                      _InfoRow('Reorder Point', item.reorderPoint.toStringAsFixed(2)),
                    ],
                  ),
                ),
              ),

              const SizedBox(height: 16),

              // Current stock balances
              Row(
                children: [
                  Icon(Icons.warehouse_outlined, size: 20, color: theme.colorScheme.primary),
                  const SizedBox(width: 8),
                  Text('Stock Balances', style: theme.textTheme.titleMedium),
                ],
              ),
              const SizedBox(height: 8),
              StreamBuilder<List<StockBalance>>(
                stream: ref.read(inventoryRepositoryProvider).watchBalances(itemId: itemId),
                builder: (context, snapshot) {
                  if (snapshot.connectionState == ConnectionState.waiting) {
                    return const Center(child: Padding(
                      padding: EdgeInsets.all(16),
                      child: CircularProgressIndicator(),
                    ));
                  }
                  final balances = snapshot.data ?? [];
                  if (balances.isEmpty) {
                    return Card(
                      child: Padding(
                        padding: const EdgeInsets.all(24),
                        child: Center(
                          child: Column(
                            children: [
                              Icon(Icons.inventory_2_outlined,
                                  size: 32, color: theme.colorScheme.outline),
                              const SizedBox(height: 8),
                              Text(
                                'No stock records',
                                style: theme.textTheme.bodyMedium?.copyWith(
                                  color: theme.colorScheme.outline,
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                    );
                  }
                  return Card(
                    child: Column(
                      children: balances.asMap().entries.map((entry) {
                        final b = entry.value;
                        final available = b.qtyOnHand - b.qtyReserved;
                        final isLow = b.qtyOnHand < item.minimumStock && item.minimumStock > 0;
                        return ListTile(
                          leading: Container(
                            width: 40,
                            height: 40,
                            decoration: BoxDecoration(
                              color: isLow
                                  ? Colors.red.withAlpha(25)
                                  : Colors.green.withAlpha(25),
                              borderRadius: BorderRadius.circular(10),
                            ),
                            child: Icon(
                              Icons.location_on_outlined,
                              color: isLow ? Colors.red : Colors.green,
                              size: 22,
                            ),
                          ),
                          title: Text('Location #${b.locationId}'),
                          subtitle: Row(
                            children: [
                              Text('On hand: ${b.qtyOnHand.toStringAsFixed(2)}'),
                              if (b.qtyReserved > 0) ...[
                                const SizedBox(width: 8),
                                Text(
                                  'Reserved: ${b.qtyReserved.toStringAsFixed(2)}',
                                  style: TextStyle(color: Colors.orange[700], fontSize: 12),
                                ),
                              ],
                            ],
                          ),
                          trailing: Column(
                            mainAxisAlignment: MainAxisAlignment.center,
                            crossAxisAlignment: CrossAxisAlignment.end,
                            children: [
                              Text(
                                available.toStringAsFixed(2),
                                style: theme.textTheme.titleSmall?.copyWith(
                                  fontWeight: FontWeight.bold,
                                  color: available > 0 ? Colors.green : Colors.red,
                                ),
                              ),
                              Text(
                                'Available',
                                style: theme.textTheme.labelSmall?.copyWith(
                                  color: theme.colorScheme.outline,
                                ),
                              ),
                            ],
                          ),
                        );
                      }).toList(),
                    ),
                  );
                },
              ),
              const SizedBox(height: 24),
            ],
          ),
          ),
        );
      },
    );
  }
}

class _PriceBox extends StatelessWidget {
  final String label;
  final String value;
  final Color color;

  const _PriceBox({required this.label, required this.value, required this.color});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: color.withAlpha(15),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        children: [
          Text(label, style: theme.textTheme.labelSmall?.copyWith(color: theme.colorScheme.outline)),
          const SizedBox(height: 4),
          Text(
            value,
            style: theme.textTheme.titleMedium?.copyWith(
              fontWeight: FontWeight.bold,
              color: color,
            ),
          ),
        ],
      ),
    );
  }
}

class _InfoRow extends StatelessWidget {
  final String label;
  final String value;

  const _InfoRow(this.label, this.value);

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 5),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label, style: theme.textTheme.bodyMedium?.copyWith(color: theme.colorScheme.outline)),
          Text(value, style: theme.textTheme.bodyMedium?.copyWith(fontWeight: FontWeight.w500)),
        ],
      ),
    );
  }
}
