import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../sync/sync_engine.dart';
import '../services/connectivity_service.dart';

class SyncStatusWidget extends ConsumerWidget {
  const SyncStatusWidget({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final syncState = ref.watch(syncStateProvider);
    final connectivity = ref.watch(connectivityStreamProvider);

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 8),
      child: syncState.when(
        data: (state) {
          switch (state.status) {
            case SyncStatus.syncing:
              return const SizedBox(
                width: 20,
                height: 20,
                child: CircularProgressIndicator(strokeWidth: 2),
              );
            case SyncStatus.error:
              return IconButton(
                icon: const Icon(Icons.sync_problem, color: Colors.red),
                tooltip: state.errorMessage ?? 'Sync error',
                onPressed: () => ref.read(syncEngineProvider).syncIfNeeded(),
              );
            case SyncStatus.offline:
              return const Tooltip(
                message: 'Offline — changes will sync when connected',
                child: Icon(Icons.cloud_off, color: Colors.orange),
              );
            case SyncStatus.idle:
              final hasChanges = state.pendingChanges > 0;
              return IconButton(
                icon: Icon(
                  hasChanges ? Icons.cloud_upload : Icons.cloud_done,
                  color: hasChanges ? Colors.orange : Colors.green,
                ),
                tooltip: hasChanges
                    ? '${state.pendingChanges} pending changes'
                    : 'All synced',
                onPressed: () => ref.read(syncEngineProvider).syncIfNeeded(),
              );
          }
        },
        loading: () => const SizedBox(
          width: 20,
          height: 20,
          child: CircularProgressIndicator(strokeWidth: 2),
        ),
        error: (_, __) => const Icon(Icons.sync_problem, color: Colors.red),
      ),
    );
  }
}
