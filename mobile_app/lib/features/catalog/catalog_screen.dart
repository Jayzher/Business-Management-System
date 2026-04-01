import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../database/app_database.dart';
import '../../repositories/catalog_repository.dart';
import '../../sync/sync_engine.dart';
import '../../widgets/sync_status_widget.dart';
import '../../widgets/empty_state.dart';
import '../../utils/responsive.dart';

final _searchQueryProvider = StateProvider<String>((ref) => '');
final _itemTypeFilterProvider = StateProvider<String?>((ref) => null);

final _filteredItemsProvider = StreamProvider<List<Item>>((ref) {
  final search = ref.watch(_searchQueryProvider);
  final itemType = ref.watch(_itemTypeFilterProvider);
  return ref.watch(catalogRepositoryProvider).watchItems(
        search: search.isEmpty ? null : search,
        itemType: itemType,
      );
});

class CatalogScreen extends ConsumerStatefulWidget {
  const CatalogScreen({super.key});

  @override
  ConsumerState<CatalogScreen> createState() => _CatalogScreenState();
}

class _CatalogScreenState extends ConsumerState<CatalogScreen> {
  final _searchController = TextEditingController();

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final items = ref.watch(_filteredItemsProvider);
    final searchQuery = ref.watch(_searchQueryProvider);
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Catalog'),
        actions: const [SyncStatusWidget(), SizedBox(width: 8)],
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(60),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            child: TextField(
              controller: _searchController,
              decoration: InputDecoration(
                hintText: 'Search items by name, code, or barcode...',
                prefixIcon: const Icon(Icons.search),
                suffixIcon: searchQuery.isNotEmpty
                    ? IconButton(
                        icon: const Icon(Icons.clear),
                        onPressed: () {
                          _searchController.clear();
                          ref.read(_searchQueryProvider.notifier).state = '';
                        },
                      )
                    : const Icon(Icons.qr_code_scanner_outlined),
                isDense: true,
              ),
              onChanged: (v) => ref.read(_searchQueryProvider.notifier).state = v,
            ),
          ),
        ),
      ),
      body: Column(
        children: [
          // Filter chips
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            padding: Responsive.horizontalPadding(context).add(const EdgeInsets.symmetric(vertical: 8)),
            child: Row(
              children: [
                _FilterChip(label: 'All', value: null, provider: _itemTypeFilterProvider),
                const SizedBox(width: 8),
                _FilterChip(label: 'Raw Materials', value: 'RAW', provider: _itemTypeFilterProvider),
                const SizedBox(width: 8),
                _FilterChip(label: 'Finished', value: 'FINISHED', provider: _itemTypeFilterProvider),
                const SizedBox(width: 8),
                _FilterChip(label: 'Service', value: 'SERVICE', provider: _itemTypeFilterProvider),
              ],
            ),
          ),

          // Item count
          items.whenData((list) {
            return Padding(
              padding: Responsive.horizontalPadding(context),
              child: Align(
                alignment: Alignment.centerLeft,
                child: Text(
                  '${list.length} item${list.length == 1 ? '' : 's'}',
                  style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.outline),
                ),
              ),
            );
          }).valueOrNull ?? const SizedBox.shrink(),

          // Item list
          Expanded(
            child: items.when(
              data: (list) {
                if (list.isEmpty) {
                  return EmptyState(
                    icon: searchQuery.isNotEmpty
                        ? Icons.search_off
                        : Icons.inventory_2_outlined,
                    title: searchQuery.isNotEmpty ? 'No Results' : 'No Items Yet',
                    subtitle: searchQuery.isNotEmpty
                        ? 'Try a different search term'
                        : 'Items will appear here after syncing',
                    actionLabel: searchQuery.isNotEmpty ? 'Clear Search' : null,
                    onAction: searchQuery.isNotEmpty
                        ? () {
                            _searchController.clear();
                            ref.read(_searchQueryProvider.notifier).state = '';
                          }
                        : null,
                  );
                }
                return RefreshIndicator(
                  onRefresh: () async {
                    await ref.read(syncEngineProvider).syncIfNeeded();
                  },
                  child: ListView.separated(
                    itemCount: list.length,
                    padding: const EdgeInsets.symmetric(vertical: 4),
                    separatorBuilder: (_, __) => const Divider(indent: 72, endIndent: 16),
                    itemBuilder: (context, index) {
                      final item = list[index];
                      return _CatalogItemTile(item: item);
                    },
                  ),
                );
              },
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (e, _) => Center(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Icon(Icons.error_outline, size: 48, color: Colors.red),
                    const SizedBox(height: 12),
                    Text('Failed to load items'),
                    const SizedBox(height: 8),
                    FilledButton.tonal(
                      onPressed: () => ref.invalidate(_filteredItemsProvider),
                      child: const Text('Retry'),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _CatalogItemTile extends StatelessWidget {
  final Item item;
  const _CatalogItemTile({required this.item});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final typeColor = switch (item.itemType) {
      'RAW' => Colors.orange,
      'FINISHED' => Colors.blue,
      'SERVICE' => Colors.purple,
      _ => Colors.grey,
    };

    return ListTile(
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
      leading: Container(
        width: 48,
        height: 48,
        decoration: BoxDecoration(
          color: typeColor.withAlpha(25),
          borderRadius: BorderRadius.circular(12),
        ),
        child: Center(
          child: Text(
            item.code.substring(0, item.code.length.clamp(0, 2)).toUpperCase(),
            style: TextStyle(
              fontWeight: FontWeight.bold,
              color: typeColor,
              fontSize: 16,
            ),
          ),
        ),
      ),
      title: Text(
        item.name,
        style: theme.textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w600),
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
      ),
      subtitle: Row(
        children: [
          Text(item.code, style: theme.textTheme.bodySmall),
          const SizedBox(width: 8),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
            decoration: BoxDecoration(
              color: typeColor.withAlpha(20),
              borderRadius: BorderRadius.circular(4),
            ),
            child: Text(
              item.itemType,
              style: theme.textTheme.labelSmall?.copyWith(
                color: typeColor,
                fontWeight: FontWeight.w600,
                fontSize: 10,
              ),
            ),
          ),
        ],
      ),
      trailing: Text(
        '₱${item.sellingPrice.toStringAsFixed(2)}',
        style: theme.textTheme.titleSmall?.copyWith(
          color: theme.colorScheme.primary,
          fontWeight: FontWeight.bold,
        ),
      ),
      onTap: () {
        HapticFeedback.selectionClick();
        context.go('/catalog/${item.id}');
      },
    );
  }
}

class _FilterChip extends ConsumerWidget {
  final String label;
  final String? value;
  final StateProvider<String?> provider;

  const _FilterChip({required this.label, required this.value, required this.provider});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final selected = ref.watch(provider) == value;
    return FilterChip(
      label: Text(label),
      selected: selected,
      onSelected: (_) {
        HapticFeedback.selectionClick();
        ref.read(provider.notifier).state = value;
      },
    );
  }
}
