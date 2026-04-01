import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../services/connectivity_service.dart';

class OfflineIndicator extends ConsumerWidget {
  const OfflineIndicator({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final connectivity = ref.watch(connectivityStreamProvider);

    return connectivity.when(
      data: (status) {
        if (status == ConnectionStatus.online) return const SizedBox.shrink();
        return MaterialBanner(
          content: const Text('You are offline. Changes will be saved locally and synced when connected.'),
          leading: const Icon(Icons.wifi_off, color: Colors.orange),
          backgroundColor: Colors.orange.shade50,
          actions: [
            TextButton(
              onPressed: () {},
              child: const Text('DISMISS'),
            ),
          ],
        );
      },
      loading: () => const SizedBox.shrink(),
      error: (_, __) => const SizedBox.shrink(),
    );
  }
}
