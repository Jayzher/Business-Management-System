import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../database/app_database.dart';
import '../../repositories/partners_repository.dart';
import '../../sync/sync_engine.dart';
import '../../widgets/sync_status_widget.dart';
import '../../widgets/empty_state.dart';
import '../../utils/responsive.dart';
import 'partner_detail_screen.dart';

final _customerSearchProvider = StateProvider<String>((ref) => '');
final _supplierSearchProvider = StateProvider<String>((ref) => '');

class PartnersScreen extends ConsumerWidget {
  const PartnersScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return DefaultTabController(
      length: 2,
      child: Scaffold(
        appBar: AppBar(
          title: const Text('Partners'),
          actions: const [SyncStatusWidget(), SizedBox(width: 8)],
          bottom: const TabBar(
            tabs: [
              Tab(icon: Icon(Icons.people_outline), text: 'Customers'),
              Tab(icon: Icon(Icons.local_shipping_outlined), text: 'Suppliers'),
            ],
          ),
        ),
        body: TabBarView(
          children: [
            _CustomerList(),
            _SupplierList(),
          ],
        ),
      ),
    );
  }
}

class _CustomerList extends ConsumerStatefulWidget {
  @override
  ConsumerState<_CustomerList> createState() => _CustomerListState();
}

class _CustomerListState extends ConsumerState<_CustomerList> {
  final _searchController = TextEditingController();

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final searchQuery = ref.watch(_customerSearchProvider);
    final customers = ref.watch(
      StreamProvider((ref) => ref.watch(partnersRepositoryProvider)
          .watchCustomers(search: searchQuery.isEmpty ? null : searchQuery)),
    );
    final theme = Theme.of(context);

    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
          child: TextField(
            controller: _searchController,
            decoration: InputDecoration(
              hintText: 'Search customers...',
              prefixIcon: const Icon(Icons.search),
              suffixIcon: searchQuery.isNotEmpty
                  ? IconButton(
                      icon: const Icon(Icons.clear),
                      onPressed: () {
                        _searchController.clear();
                        ref.read(_customerSearchProvider.notifier).state = '';
                      },
                    )
                  : null,
              isDense: true,
            ),
            onChanged: (v) => ref.read(_customerSearchProvider.notifier).state = v,
          ),
        ),
        Expanded(
          child: customers.when(
            data: (list) {
              if (list.isEmpty) {
                return EmptyState(
                  icon: searchQuery.isNotEmpty ? Icons.search_off : Icons.people_outline,
                  title: searchQuery.isNotEmpty ? 'No Results' : 'No Customers',
                  subtitle: searchQuery.isNotEmpty
                      ? 'Try a different search term'
                      : 'Customers will appear after syncing',
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
                    final c = list[index];
                    return _PartnerTile(
                      name: c.name,
                      code: c.code,
                      city: c.city,
                      phone: c.phone,
                      isCustomer: true,
                      onTap: () {
                        HapticFeedback.selectionClick();
                        Navigator.of(context).push(MaterialPageRoute(
                          builder: (_) => PartnerDetailScreen(
                            type: 'customer',
                            name: c.name,
                            code: c.code,
                            phone: c.phone,
                            email: c.email,
                            address: c.address,
                            city: c.city,
                            taxId: c.taxId,
                            contactPerson: c.contactPerson,
                          ),
                        ));
                      },
                    );
                  },
                ),
              );
            },
            loading: () => const Center(child: CircularProgressIndicator()),
            error: (e, _) => Center(child: Text('Error: $e')),
          ),
        ),
      ],
    );
  }
}

class _SupplierList extends ConsumerStatefulWidget {
  @override
  ConsumerState<_SupplierList> createState() => _SupplierListState();
}

class _SupplierListState extends ConsumerState<_SupplierList> {
  final _searchController = TextEditingController();

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final searchQuery = ref.watch(_supplierSearchProvider);
    final suppliers = ref.watch(
      StreamProvider((ref) => ref.watch(partnersRepositoryProvider)
          .watchSuppliers(search: searchQuery.isEmpty ? null : searchQuery)),
    );
    final theme = Theme.of(context);

    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
          child: TextField(
            controller: _searchController,
            decoration: InputDecoration(
              hintText: 'Search suppliers...',
              prefixIcon: const Icon(Icons.search),
              suffixIcon: searchQuery.isNotEmpty
                  ? IconButton(
                      icon: const Icon(Icons.clear),
                      onPressed: () {
                        _searchController.clear();
                        ref.read(_supplierSearchProvider.notifier).state = '';
                      },
                    )
                  : null,
              isDense: true,
            ),
            onChanged: (v) => ref.read(_supplierSearchProvider.notifier).state = v,
          ),
        ),
        Expanded(
          child: suppliers.when(
            data: (list) {
              if (list.isEmpty) {
                return EmptyState(
                  icon: searchQuery.isNotEmpty ? Icons.search_off : Icons.local_shipping_outlined,
                  title: searchQuery.isNotEmpty ? 'No Results' : 'No Suppliers',
                  subtitle: searchQuery.isNotEmpty
                      ? 'Try a different search term'
                      : 'Suppliers will appear after syncing',
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
                    final s = list[index];
                    return _PartnerTile(
                      name: s.name,
                      code: s.code,
                      city: s.city,
                      phone: s.phone,
                      isCustomer: false,
                      onTap: () {
                        HapticFeedback.selectionClick();
                        Navigator.of(context).push(MaterialPageRoute(
                          builder: (_) => PartnerDetailScreen(
                            type: 'supplier',
                            name: s.name,
                            code: s.code,
                            phone: s.phone,
                            email: s.email,
                            address: s.address,
                            city: s.city,
                            taxId: s.taxId,
                            contactPerson: s.contactPerson,
                          ),
                        ));
                      },
                    );
                  },
                ),
              );
            },
            loading: () => const Center(child: CircularProgressIndicator()),
            error: (e, _) => Center(child: Text('Error: $e')),
          ),
        ),
      ],
    );
  }
}

class _PartnerTile extends StatelessWidget {
  final String name;
  final String code;
  final String city;
  final String phone;
  final bool isCustomer;
  final VoidCallback onTap;

  const _PartnerTile({
    required this.name,
    required this.code,
    required this.city,
    required this.phone,
    required this.isCustomer,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final color = isCustomer ? Colors.purple : Colors.blue;

    return ListTile(
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 2),
      leading: CircleAvatar(
        backgroundColor: color.withAlpha(25),
        foregroundColor: color,
        child: Text(
          _initials(name),
          style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 14),
        ),
      ),
      title: Text(
        name,
        style: theme.textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w600),
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
      ),
      subtitle: Text(
        '$code${city.isNotEmpty ? " • $city" : ""}',
        style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.outline),
      ),
      trailing: phone.isNotEmpty
          ? Icon(Icons.phone_outlined, size: 18, color: theme.colorScheme.outline)
          : null,
      onTap: onTap,
    );
  }

  String _initials(String name) {
    final parts = name.trim().split(' ');
    if (parts.length >= 2) {
      return '${parts.first[0]}${parts.last[0]}'.toUpperCase();
    }
    return name.substring(0, name.length.clamp(0, 2)).toUpperCase();
  }
}
