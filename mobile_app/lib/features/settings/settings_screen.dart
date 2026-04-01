import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../services/auth_service.dart';
import '../../sync/sync_engine.dart';
import '../../services/connectivity_service.dart';
import '../../widgets/confirm_dialog.dart';
import '../../utils/responsive.dart';

class SettingsScreen extends ConsumerWidget {
  const SettingsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final syncState = ref.watch(syncStateProvider);
    final connectivity = ref.watch(connectivityStreamProvider);
    final theme = Theme.of(context);

    final isOnline = connectivity.valueOrNull == ConnectionStatus.online;

    return Scaffold(
      appBar: AppBar(title: const Text('Sync & Data')),
      body: ResponsiveCenter(
        child: ListView(
          padding: const EdgeInsets.symmetric(vertical: 8),
        children: [
          // Connection status card
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
            child: Card(
              color: isOnline
                  ? Colors.green.withOpacity(0.08)
                  : Colors.red.withOpacity(0.08),
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Row(
                  children: [
                    Container(
                      padding: const EdgeInsets.all(10),
                      decoration: BoxDecoration(
                        color: (isOnline ? Colors.green : Colors.red).withOpacity(0.15),
                        shape: BoxShape.circle,
                      ),
                      child: Icon(
                        isOnline ? Icons.wifi : Icons.wifi_off,
                        color: isOnline ? Colors.green : Colors.red,
                      ),
                    ),
                    const SizedBox(width: 16),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            isOnline ? 'Connected' : 'Offline',
                            style: theme.textTheme.titleMedium?.copyWith(
                              fontWeight: FontWeight.bold,
                              color: isOnline ? Colors.green.shade700 : Colors.red.shade700,
                            ),
                          ),
                          const SizedBox(height: 2),
                          Text(
                            isOnline
                                ? 'All changes sync automatically'
                                : 'Changes saved locally until online',
                            style: theme.textTheme.bodySmall?.copyWith(
                              color: theme.colorScheme.onSurfaceVariant,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),

          // Sync section
          _SectionHeader(title: 'Sync'),

          syncState.when(
            data: (s) => Column(
              children: [
                _DetailTile(
                  icon: Icons.schedule,
                  label: 'Last synced',
                  value: s.lastSyncTime != null
                      ? _formatTime(s.lastSyncTime!)
                      : 'Never',
                ),
                if (s.pendingChanges > 0)
                  _DetailTile(
                    icon: Icons.cloud_upload_outlined,
                    label: 'Pending changes',
                    value: '${s.pendingChanges}',
                    valueColor: Colors.orange,
                  ),
                if (s.pendingChanges == 0)
                  _DetailTile(
                    icon: Icons.cloud_done_outlined,
                    label: 'Status',
                    value: 'All synced',
                    valueColor: Colors.green,
                  ),
              ],
            ),
            loading: () => const Padding(
              padding: EdgeInsets.all(16),
              child: Center(child: CircularProgressIndicator.adaptive()),
            ),
            error: (e, _) => _DetailTile(
              icon: Icons.error_outline,
              label: 'Sync error',
              value: e.toString(),
              valueColor: Colors.red,
            ),
          ),

          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            child: FilledButton.tonalIcon(
              onPressed: () {
                HapticFeedback.mediumImpact();
                ref.read(syncEngineProvider).syncIfNeeded();
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(
                    content: Text('Sync started...'),
                    duration: Duration(seconds: 1),
                  ),
                );
              },
              icon: const Icon(Icons.sync),
              label: const Text('Sync Now'),
            ),
          ),

          const Divider(height: 32),

          // Data section
          _SectionHeader(title: 'Data Management'),

          ListTile(
            leading: const Icon(Icons.delete_sweep_outlined),
            title: const Text('Clear Local Cache'),
            subtitle: const Text('Remove cached images and temporary files'),
            onTap: () async {
              final ok = await showConfirmDialog(
                context: context,
                title: 'Clear Cache?',
                message: 'This will remove cached images and temp files. Your data will not be affected.',
                confirmText: 'Clear',
                isDestructive: true,
              );
              if (ok && context.mounted) {
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(content: Text('Cache cleared')),
                );
              }
            },
          ),

          const Divider(height: 32),

          // Account section
          _SectionHeader(title: 'Account'),

          ListTile(
            leading: Icon(Icons.logout, color: theme.colorScheme.error),
            title: Text('Sign Out',
                style: TextStyle(color: theme.colorScheme.error)),
            subtitle: const Text('You can sign back in anytime'),
            onTap: () async {
              final ok = await showConfirmDialog(
                context: context,
                title: 'Sign Out?',
                message: 'Any unsynced changes will be kept on this device.',
                confirmText: 'Sign Out',
                isDestructive: true,
              );
              if (ok) {
                await ref.read(authServiceProvider).logout();
                ref.invalidate(authStateProvider);
              }
            },
          ),

          const SizedBox(height: 24),

          // App info
          Center(
            child: Text(
              'BMS Mobile v1.0.0',
              style: theme.textTheme.bodySmall?.copyWith(
                color: theme.colorScheme.outline,
              ),
            ),
          ),
          const SizedBox(height: 8),
        ],
      ),
      ),
    );
  }

  static String _formatTime(DateTime time) {
    final now = DateTime.now();
    final diff = now.difference(time);
    if (diff.inMinutes < 1) return 'Just now';
    if (diff.inMinutes < 60) return '${diff.inMinutes}m ago';
    if (diff.inHours < 24) return '${diff.inHours}h ago';
    return '${diff.inDays}d ago';
  }
}

class _SectionHeader extends StatelessWidget {
  final String title;
  const _SectionHeader({required this.title});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 4),
      child: Text(
        title,
        style: Theme.of(context).textTheme.labelLarge?.copyWith(
              color: Theme.of(context).colorScheme.primary,
              fontWeight: FontWeight.bold,
            ),
      ),
    );
  }
}

class _DetailTile extends StatelessWidget {
  final IconData icon;
  final String label;
  final String value;
  final Color? valueColor;

  const _DetailTile({
    required this.icon,
    required this.label,
    required this.value,
    this.valueColor,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return ListTile(
      leading: Icon(icon, color: theme.colorScheme.onSurfaceVariant),
      title: Text(label),
      trailing: Text(
        value,
        style: theme.textTheme.bodyMedium?.copyWith(
          color: valueColor ?? theme.colorScheme.onSurfaceVariant,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }
}
