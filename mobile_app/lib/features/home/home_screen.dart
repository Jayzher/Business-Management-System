import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../database/app_database.dart';
import '../../repositories/catalog_repository.dart';
import '../../repositories/inventory_repository.dart';
import '../../repositories/pos_repository.dart';
import '../../repositories/partners_repository.dart';
import '../../sync/sync_engine.dart';
import '../../widgets/sync_status_widget.dart';
import '../../widgets/offline_indicator.dart';
import '../../utils/responsive.dart';

// Dashboard data providers
final _todaySalesCountProvider = StreamProvider<int>((ref) {
  return ref.watch(posRepositoryProvider).watchTodaySales().map((l) => l.length);
});

final _todayRevenueProvider = StreamProvider<double>((ref) {
  return ref.watch(posRepositoryProvider).watchTodaySales().map(
        (sales) => sales.fold(0.0, (sum, s) => sum + s.total),
      );
});

final _itemCountProvider = StreamProvider<int>((ref) {
  return ref.watch(catalogRepositoryProvider).watchItems().map((l) => l.length);
});

final _customerCountProvider = StreamProvider<int>((ref) {
  return ref.watch(partnersRepositoryProvider).watchCustomers().map((l) => l.length);
});

class HomeScreen extends ConsumerWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final todaySales = ref.watch(_todaySalesCountProvider);
    final todayRevenue = ref.watch(_todayRevenueProvider);
    final itemCount = ref.watch(_itemCountProvider);
    final customerCount = ref.watch(_customerCountProvider);

    return Scaffold(
      appBar: AppBar(
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Dashboard', style: theme.textTheme.titleLarge?.copyWith(fontWeight: FontWeight.bold)),
            Text(
              _greeting(),
              style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.outline),
            ),
          ],
        ),
        toolbarHeight: 64,
        actions: const [SyncStatusWidget(), SizedBox(width: 8)],
      ),
      body: RefreshIndicator(
        onRefresh: () async {
          await ref.read(syncEngineProvider).syncIfNeeded();
        },
        child: ListView(
          padding: Responsive.bodyPadding(context).add(const EdgeInsets.only(bottom: 24)),
          children: [
            // Offline indicator
            const OfflineIndicator(),

            // Stats — use a responsive wrap: 2 cols on compact, 4 cols on medium+
            const SizedBox(height: 8),
            _buildStatCards(context, todaySales, todayRevenue, itemCount, customerCount),

            // Quick actions section
            const SizedBox(height: 28),
            Text(
              'Quick Actions',
              style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w600),
            ),
            const SizedBox(height: 12),
            _QuickActionBanner(
              icon: Icons.point_of_sale,
              title: 'Open POS',
              subtitle: 'Start selling — works offline',
              color: Colors.blue,
              onTap: () {
                HapticFeedback.lightImpact();
                context.go('/pos');
              },
            ),

            const SizedBox(height: 24),
            Text(
              'Modules',
              style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w600),
            ),
            const SizedBox(height: 12),
            GridView.count(
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              crossAxisCount: Responsive.gridColumns(context, compact: 3, medium: 4, expanded: 6),
              mainAxisSpacing: 12,
              crossAxisSpacing: 12,
              childAspectRatio: 1.0,
              children: [
                _ModuleCard(
                  icon: Icons.inventory_2_outlined,
                  label: 'Catalog',
                  color: Colors.teal,
                  onTap: () => context.go('/catalog'),
                ),
                _ModuleCard(
                  icon: Icons.warehouse_outlined,
                  label: 'Inventory',
                  color: Colors.orange,
                  onTap: () => context.go('/inventory'),
                ),
                _ModuleCard(
                  icon: Icons.people_outline,
                  label: 'Partners',
                  color: Colors.purple,
                  onTap: () => context.go('/partners'),
                ),
                _ModuleCard(
                  icon: Icons.receipt_long_outlined,
                  label: 'Sales',
                  color: Colors.green,
                  onTap: () => context.go('/sales'),
                ),
                _ModuleCard(
                  icon: Icons.history,
                  label: 'History',
                  color: Colors.indigo,
                  onTap: () => context.go('/transactions'),
                ),
                _ModuleCard(
                  icon: Icons.settings_outlined,
                  label: 'Settings',
                  color: Colors.grey,
                  onTap: () => context.go('/settings'),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  String _greeting() {
    final hour = DateTime.now().hour;
    if (hour < 12) return 'Good morning';
    if (hour < 17) return 'Good afternoon';
    return 'Good evening';
  }

  Widget _buildStatCards(
    BuildContext context,
    AsyncValue<int> todaySales,
    AsyncValue<double> todayRevenue,
    AsyncValue<int> itemCount,
    AsyncValue<int> customerCount,
  ) {
    final cards = [
      _StatCard(
        icon: Icons.receipt_outlined,
        label: "Today's Sales",
        value: todaySales.when(data: (c) => '$c', loading: () => '—', error: (_, __) => '—'),
        color: Colors.blue,
      ),
      _StatCard(
        icon: Icons.payments_outlined,
        label: 'Revenue',
        value: todayRevenue.when(data: (r) => '₱${_formatCurrency(r)}', loading: () => '—', error: (_, __) => '—'),
        color: Colors.green,
      ),
      _StatCard(
        icon: Icons.inventory_2_outlined,
        label: 'Catalog Items',
        value: itemCount.when(data: (c) => '$c', loading: () => '—', error: (_, __) => '—'),
        color: Colors.teal,
      ),
      _StatCard(
        icon: Icons.people_outline,
        label: 'Customers',
        value: customerCount.when(data: (c) => '$c', loading: () => '—', error: (_, __) => '—'),
        color: Colors.purple,
      ),
    ];

    final cols = Responsive.value<int>(context, compact: 2, medium: 4, expanded: 4);
    if (cols == 4) {
      return Row(
        children: [
          for (int i = 0; i < cards.length; i++) ...[
            if (i > 0) const SizedBox(width: 12),
            Expanded(child: cards[i]),
          ],
        ],
      );
    }
    // 2-column layout (compact)
    return Column(
      children: [
        Row(children: [Expanded(child: cards[0]), const SizedBox(width: 12), Expanded(child: cards[1])]),
        const SizedBox(height: 12),
        Row(children: [Expanded(child: cards[2]), const SizedBox(width: 12), Expanded(child: cards[3])]),
      ],
    );
  }

  String _formatCurrency(double amount) {
    if (amount >= 1000000) return '${(amount / 1000000).toStringAsFixed(1)}M';
    if (amount >= 1000) return '${(amount / 1000).toStringAsFixed(1)}K';
    return amount.toStringAsFixed(2);
  }
}

class _StatCard extends StatelessWidget {
  final IconData icon;
  final String label;
  final String value;
  final Color color;

  const _StatCard({
    required this.icon,
    required this.label,
    required this.value,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Container(
                  width: 32,
                  height: 32,
                  decoration: BoxDecoration(
                    color: color.withAlpha(30),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Icon(icon, size: 18, color: color),
                ),
                const Spacer(),
              ],
            ),
            const SizedBox(height: 10),
            Text(
              value,
              style: theme.textTheme.titleLarge?.copyWith(fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 2),
            Text(
              label,
              style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.outline),
            ),
          ],
        ),
      ),
    );
  }
}

class _QuickActionBanner extends StatelessWidget {
  final IconData icon;
  final String title;
  final String subtitle;
  final Color color;
  final VoidCallback onTap;

  const _QuickActionBanner({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.color,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      color: color,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(16),
        child: Padding(
          padding: const EdgeInsets.all(18),
          child: Row(
            children: [
              Container(
                width: 48,
                height: 48,
                decoration: BoxDecoration(
                  color: Colors.white.withAlpha(50),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Icon(icon, color: Colors.white, size: 28),
              ),
              const SizedBox(width: 16),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(title,
                        style: theme.textTheme.titleMedium?.copyWith(
                          color: Colors.white,
                          fontWeight: FontWeight.bold,
                        )),
                    Text(subtitle,
                        style: theme.textTheme.bodySmall?.copyWith(
                          color: Colors.white.withAlpha(200),
                        )),
                  ],
                ),
              ),
              const Icon(Icons.arrow_forward_ios, color: Colors.white70, size: 18),
            ],
          ),
        ),
      ),
    );
  }
}

class _ModuleCard extends StatelessWidget {
  final IconData icon;
  final String label;
  final Color color;
  final VoidCallback onTap;

  const _ModuleCard({
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
        onTap: () {
          HapticFeedback.lightImpact();
          onTap();
        },
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
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
              const SizedBox(height: 8),
              Text(
                label,
                style: theme.textTheme.labelMedium?.copyWith(fontWeight: FontWeight.w600),
                textAlign: TextAlign.center,
              ),
            ],
          ),
        ),
      ),
    );
  }
}
