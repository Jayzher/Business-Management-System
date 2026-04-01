import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../services/connectivity_service.dart';
import '../../widgets/sync_status_widget.dart';
import '../../utils/responsive.dart';

class MoreScreen extends ConsumerWidget {
  const MoreScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final connectivity = ref.watch(connectivityStreamProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('More'),
        actions: const [SyncStatusWidget()],
      ),
      body: ResponsiveCenter(
        child: ListView(
        padding: const EdgeInsets.symmetric(vertical: 8),
        children: [
          // Status banner
          connectivity.when(
            data: (s) {
              if (s == ConnectionStatus.online) return const SizedBox.shrink();
              return Container(
                margin: const EdgeInsets.fromLTRB(16, 0, 16, 12),
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                decoration: BoxDecoration(
                  color: Colors.orange.withAlpha(30),
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: Colors.orange.withAlpha(80)),
                ),
                child: Row(
                  children: [
                    const Icon(Icons.wifi_off, color: Colors.orange, size: 20),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Text(
                        'Offline mode — changes sync when reconnected',
                        style: theme.textTheme.bodySmall?.copyWith(color: Colors.orange[800]),
                      ),
                    ),
                  ],
                ),
              );
            },
            loading: () => const SizedBox.shrink(),
            error: (_, __) => const SizedBox.shrink(),
          ),

          // Menu sections
          _SectionHeader(title: 'Business'),
          _MenuTile(
            icon: Icons.people_outline,
            iconColor: Colors.purple,
            title: 'Partners',
            subtitle: 'Customers & suppliers',
            onTap: () => context.go('/partners'),
          ),
          _MenuTile(
            icon: Icons.receipt_long_outlined,
            iconColor: Colors.green,
            title: 'Sales Orders',
            subtitle: 'Create & manage orders',
            onTap: () => context.go('/sales'),
          ),
          _MenuTile(
            icon: Icons.history,
            iconColor: Colors.blue,
            title: 'Transaction History',
            subtitle: 'View past POS sales',
            onTap: () => context.go('/transactions'),
          ),

          const SizedBox(height: 8),
          _SectionHeader(title: 'System'),
          _MenuTile(
            icon: Icons.sync_outlined,
            iconColor: Colors.teal,
            title: 'Sync & Data',
            subtitle: 'Connection status & sync controls',
            onTap: () => context.go('/settings'),
          ),
          _MenuTile(
            icon: Icons.info_outline,
            iconColor: Colors.grey,
            title: 'About',
            subtitle: 'App version & info',
            onTap: () => _showAbout(context),
          ),
        ],
      ),
      ),
    );
  }

  void _showAbout(BuildContext context) {
    showAboutDialog(
      context: context,
      applicationName: 'Business Management',
      applicationVersion: '1.0.0',
      applicationIcon: Icon(
        Icons.business,
        size: 48,
        color: Theme.of(context).colorScheme.primary,
      ),
      children: [
        const Text(
          'An offline-first business management system for POS, inventory, catalog, and sales.',
        ),
      ],
    );
  }
}

class _SectionHeader extends StatelessWidget {
  final String title;
  const _SectionHeader({required this.title});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 4),
      child: Text(
        title.toUpperCase(),
        style: Theme.of(context).textTheme.labelSmall?.copyWith(
              color: Theme.of(context).colorScheme.outline,
              fontWeight: FontWeight.w600,
              letterSpacing: 1.2,
            ),
      ),
    );
  }
}

class _MenuTile extends StatelessWidget {
  final IconData icon;
  final Color iconColor;
  final String title;
  final String subtitle;
  final VoidCallback onTap;

  const _MenuTile({
    required this.icon,
    required this.iconColor,
    required this.title,
    required this.subtitle,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return ListTile(
      leading: Container(
        width: 40,
        height: 40,
        decoration: BoxDecoration(
          color: iconColor.withAlpha(30),
          borderRadius: BorderRadius.circular(10),
        ),
        child: Icon(icon, color: iconColor, size: 22),
      ),
      title: Text(title),
      subtitle: Text(subtitle, style: Theme.of(context).textTheme.bodySmall),
      trailing: const Icon(Icons.chevron_right, size: 20),
      onTap: onTap,
    );
  }
}
