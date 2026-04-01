import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../features/auth/login_screen.dart';
import '../features/home/home_screen.dart';
import '../features/home/more_screen.dart';
import '../features/catalog/catalog_screen.dart';
import '../features/catalog/item_detail_screen.dart';
import '../features/inventory/inventory_screen.dart';
import '../features/inventory/stock_balance_screen.dart';
import '../features/inventory/stock_moves_screen.dart';
import '../features/pos/pos_screen.dart';
import '../features/pos/transaction_history_screen.dart';
import '../features/partners/partners_screen.dart';
import '../features/sales/sales_screen.dart';
import '../features/settings/settings_screen.dart';
import '../services/auth_service.dart';
import '../utils/responsive.dart';

final appRouterProvider = Provider<GoRouter>((ref) {
  final authState = ref.watch(authStateProvider);

  return GoRouter(
    initialLocation: '/login',
    redirect: (context, state) {
      final isLoggedIn = authState.valueOrNull ?? false;
      final isLoginRoute = state.matchedLocation == '/login';

      if (!isLoggedIn && !isLoginRoute) return '/login';
      if (isLoggedIn && isLoginRoute) return '/';
      return null;
    },
    routes: [
      GoRoute(path: '/login', builder: (_, __) => const LoginScreen()),
      ShellRoute(
        builder: (context, state, child) => AppShell(child: child),
        routes: [
          GoRoute(path: '/', builder: (_, __) => const HomeScreen()),
          GoRoute(path: '/catalog', builder: (_, __) => const CatalogScreen()),
          GoRoute(
            path: '/catalog/:id',
            builder: (_, state) => ItemDetailScreen(
              itemId: int.parse(state.pathParameters['id']!),
            ),
          ),
          GoRoute(path: '/inventory', builder: (_, __) => const InventoryScreen()),
          GoRoute(path: '/inventory/balances', builder: (_, __) => const StockBalanceScreen()),
          GoRoute(path: '/inventory/moves', builder: (_, __) => const StockMovesScreen()),
          GoRoute(path: '/pos', builder: (_, __) => const POSScreen()),
          GoRoute(path: '/transactions', builder: (_, __) => const TransactionHistoryScreen()),
          GoRoute(path: '/partners', builder: (_, __) => const PartnersScreen()),
          GoRoute(path: '/sales', builder: (_, __) => const SalesScreen()),
          GoRoute(path: '/settings', builder: (_, __) => const SettingsScreen()),
          GoRoute(path: '/more', builder: (_, __) => const MoreScreen()),
        ],
      ),
    ],
  );
});

class AppShell extends StatelessWidget {
  final Widget child;
  const AppShell({super.key, required this.child});

  static const _destinations = <_NavDestination>[
    _NavDestination(Icons.home_outlined, Icons.home, 'Home'),
    _NavDestination(Icons.inventory_2_outlined, Icons.inventory_2, 'Catalog'),
    _NavDestination(Icons.warehouse_outlined, Icons.warehouse, 'Inventory'),
    _NavDestination(Icons.point_of_sale_outlined, Icons.point_of_sale, 'POS'),
    _NavDestination(Icons.more_horiz, Icons.more_horiz, 'More'),
  ];

  @override
  Widget build(BuildContext context) {
    final useRail = Responsive.useNavigationRail(context);
    final selectedIndex = _calculateSelectedIndex(context);

    if (useRail) {
      return Scaffold(
        body: Row(
          children: [
            NavigationRail(
              selectedIndex: selectedIndex,
              onDestinationSelected: (i) => _onItemTapped(i, context),
              labelType: NavigationRailLabelType.all,
              destinations: _destinations
                  .map((d) => NavigationRailDestination(
                        icon: Icon(d.icon),
                        selectedIcon: Icon(d.selectedIcon),
                        label: Text(d.label),
                      ))
                  .toList(),
            ),
            const VerticalDivider(thickness: 1, width: 1),
            Expanded(child: child),
          ],
        ),
      );
    }

    return Scaffold(
      body: child,
      bottomNavigationBar: NavigationBar(
        selectedIndex: selectedIndex,
        onDestinationSelected: (index) => _onItemTapped(index, context),
        destinations: _destinations
            .map((d) => NavigationDestination(
                  icon: Icon(d.icon),
                  selectedIcon: Icon(d.selectedIcon),
                  label: d.label,
                ))
            .toList(),
      ),
    );
  }

  int _calculateSelectedIndex(BuildContext context) {
    final location = GoRouterState.of(context).matchedLocation;
    if (location.startsWith('/catalog')) return 1;
    if (location.startsWith('/inventory')) return 2;
    if (location.startsWith('/pos') || location.startsWith('/transactions')) return 3;
    if (location.startsWith('/more') ||
        location.startsWith('/partners') ||
        location.startsWith('/sales') ||
        location.startsWith('/settings')) return 4;
    return 0;
  }

  void _onItemTapped(int index, BuildContext context) {
    switch (index) {
      case 0: context.go('/');
      case 1: context.go('/catalog');
      case 2: context.go('/inventory');
      case 3: context.go('/pos');
      case 4: context.go('/more');
    }
  }
}

class _NavDestination {
  final IconData icon;
  final IconData selectedIcon;
  final String label;
  const _NavDestination(this.icon, this.selectedIcon, this.label);
}
