import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../database/app_database.dart';
import '../../repositories/catalog_repository.dart';
import '../../repositories/inventory_repository.dart';
import '../../repositories/pos_repository.dart';
import '../../services/auth_service.dart';
import '../../widgets/sync_status_widget.dart';
import '../../widgets/confirm_dialog.dart';
import '../../widgets/empty_state.dart';
import '../../utils/responsive.dart';
import 'payment_dialog.dart';
import 'receipt_screen.dart';

// ─── Cart State ───

class CartItem {
  final Item item;
  final int unitId;
  double qty;
  double unitPrice;
  double discountAmount;

  CartItem({
    required this.item,
    required this.unitId,
    this.qty = 1,
    required this.unitPrice,
    this.discountAmount = 0,
  });

  double get lineTotal => (qty * unitPrice) - discountAmount;
}

class CartState {
  final List<CartItem> items;
  final int? customerId;

  const CartState({this.items = const [], this.customerId});

  double get subtotal => items.fold(0, (sum, i) => sum + (i.qty * i.unitPrice));
  double get totalDiscount => items.fold(0, (sum, i) => sum + i.discountAmount);
  double get total => subtotal - totalDiscount;
  int get itemCount => items.length;

  CartState copyWith({List<CartItem>? items, int? customerId}) {
    return CartState(
      items: items ?? this.items,
      customerId: customerId ?? this.customerId,
    );
  }
}

class CartNotifier extends StateNotifier<CartState> {
  CartNotifier() : super(const CartState());

  void addItem(Item item, {double qty = 1, required double unitPrice, required int unitId}) {
    final existing = state.items.indexWhere((i) => i.item.id == item.id && i.unitId == unitId);
    if (existing >= 0) {
      final updated = List<CartItem>.from(state.items);
      updated[existing].qty += qty;
      state = state.copyWith(items: updated);
    } else {
      state = state.copyWith(items: [
        ...state.items,
        CartItem(item: item, unitId: unitId, qty: qty, unitPrice: unitPrice),
      ]);
    }
  }

  void updateQty(int index, double qty) {
    if (qty <= 0) {
      removeItem(index);
      return;
    }
    final updated = List<CartItem>.from(state.items);
    updated[index].qty = qty;
    state = state.copyWith(items: updated);
  }

  void removeItem(int index) {
    final updated = List<CartItem>.from(state.items);
    updated.removeAt(index);
    state = state.copyWith(items: updated);
  }

  void setCustomer(int? customerId) {
    state = state.copyWith(customerId: customerId);
  }

  void clear() {
    state = const CartState();
  }
}

final cartProvider = StateNotifierProvider<CartNotifier, CartState>((ref) => CartNotifier());

// ─── POS Screen ───

class POSScreen extends ConsumerWidget {
  const POSScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final cart = ref.watch(cartProvider);
    final theme = Theme.of(context);
    final sideBySide = Responsive.useSideBySide(context);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Point of Sale'),
        actions: [
          const SyncStatusWidget(),
          if (!sideBySide)
            Badge(
              label: Text('${cart.itemCount}'),
              isLabelVisible: cart.itemCount > 0,
              child: IconButton(
                icon: const Icon(Icons.shopping_cart_outlined),
                onPressed: () => _showCart(context, ref),
              ),
            ),
          const SizedBox(width: 8),
        ],
      ),
      body: sideBySide ? _buildWideLayout(context, ref, cart) : _buildCompactLayout(context, ref, cart),
      bottomNavigationBar: !sideBySide && cart.itemCount > 0
          ? Container(
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
              decoration: BoxDecoration(
                color: theme.colorScheme.surface,
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withAlpha(20),
                    blurRadius: 12,
                    offset: const Offset(0, -2),
                  ),
                ],
              ),
              child: SafeArea(
                child: Row(
                  children: [
                    Expanded(
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            '${cart.itemCount} item${cart.itemCount == 1 ? '' : 's'}',
                            style: theme.textTheme.bodySmall?.copyWith(
                              color: theme.colorScheme.outline,
                            ),
                          ),
                          Text(
                            '₱${cart.total.toStringAsFixed(2)}',
                            style: theme.textTheme.headlineSmall?.copyWith(
                              fontWeight: FontWeight.bold,
                            ),
                          ),
                        ],
                      ),
                    ),
                    FilledButton.icon(
                      onPressed: () => _showCart(context, ref),
                      icon: const Icon(Icons.shopping_cart_checkout),
                      label: const Text('Checkout'),
                      style: FilledButton.styleFrom(
                        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 14),
                      ),
                    ),
                  ],
                ),
              ),
            )
          : null,
    );
  }

  /// Compact (phone) layout: items only, cart in bottom sheet.
  Widget _buildCompactLayout(BuildContext context, WidgetRef ref, CartState cart) {
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 4),
          child: TextField(
            decoration: const InputDecoration(
              hintText: 'Search or scan barcode...',
              prefixIcon: Icon(Icons.search),
              suffixIcon: Icon(Icons.qr_code_scanner_outlined),
            ),
            onChanged: (v) => ref.read(_posSearchProvider.notifier).state = v,
          ),
        ),
        Expanded(child: _ItemGrid()),
      ],
    );
  }

  /// Wide (tablet) layout: items on the left, cart panel on the right.
  Widget _buildWideLayout(BuildContext context, WidgetRef ref, CartState cart) {
    return Row(
      children: [
        // Left: catalog
        Expanded(
          flex: 3,
          child: Column(
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 8, 16, 4),
                child: TextField(
                  decoration: const InputDecoration(
                    hintText: 'Search or scan barcode...',
                    prefixIcon: Icon(Icons.search),
                    suffixIcon: Icon(Icons.qr_code_scanner_outlined),
                  ),
                  onChanged: (v) => ref.read(_posSearchProvider.notifier).state = v,
                ),
              ),
              Expanded(child: _ItemGrid()),
            ],
          ),
        ),
        const VerticalDivider(width: 1),
        // Right: cart panel
        Expanded(
          flex: 2,
          child: _InlineCartPanel(),
        ),
      ],
    );
  }

  void _showCart(BuildContext context, WidgetRef ref) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      builder: (_) => ProviderScope(
        parent: ProviderScope.containerOf(context),
        child: const _CartSheet(),
      ),
    );
  }
}

final _posSearchProvider = StateProvider<String>((ref) => '');

final _posItemsProvider = StreamProvider<List<Item>>((ref) {
  final search = ref.watch(_posSearchProvider);
  return ref.watch(catalogRepositoryProvider).watchItems(
        search: search.isEmpty ? null : search,
      );
});

class _ItemGrid extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final items = ref.watch(_posItemsProvider);
    final theme = Theme.of(context);

    return items.when(
      data: (list) {
        if (list.isEmpty) {
          return const EmptyState(
            icon: Icons.inventory_2_outlined,
            title: 'No Items Found',
            subtitle: 'Try a different search or sync your catalog',
          );
        }
        return GridView.builder(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
          gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
            crossAxisCount: Responsive.gridColumns(context, compact: 2, medium: 2, expanded: 3),
            childAspectRatio: 1.15,
            crossAxisSpacing: 10,
            mainAxisSpacing: 10,
          ),
          itemCount: list.length,
          itemBuilder: (context, index) {
            final item = list[index];
            return Card(
              clipBehavior: Clip.antiAlias,
              child: InkWell(
                onTap: () {
                  ref.read(cartProvider.notifier).addItem(
                        item,
                        unitPrice: item.sellingPrice,
                        unitId: item.defaultUnitId,
                      );
                  HapticFeedback.lightImpact();
                  ScaffoldMessenger.of(context).clearSnackBars();
                  ScaffoldMessenger.of(context).showSnackBar(
                    SnackBar(
                      content: Text('${item.name} added to cart'),
                      duration: const Duration(milliseconds: 1200),
                      action: SnackBarAction(
                        label: 'Undo',
                        onPressed: () {
                          final cart = ref.read(cartProvider);
                          final idx = cart.items.lastIndexWhere((i) => i.item.id == item.id);
                          if (idx >= 0) ref.read(cartProvider.notifier).removeItem(idx);
                        },
                      ),
                    ),
                  );
                },
                child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        item.code,
                        style: theme.textTheme.labelSmall?.copyWith(
                          color: theme.colorScheme.outline,
                          fontFamily: 'monospace',
                        ),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        item.name,
                        style: theme.textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w600),
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                      ),
                      const Spacer(),
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Text(
                            '₱${item.sellingPrice.toStringAsFixed(2)}',
                            style: theme.textTheme.titleMedium?.copyWith(
                              color: theme.colorScheme.primary,
                              fontWeight: FontWeight.bold,
                            ),
                          ),
                          Container(
                            width: 28,
                            height: 28,
                            decoration: BoxDecoration(
                              color: theme.colorScheme.primaryContainer,
                              borderRadius: BorderRadius.circular(8),
                            ),
                            child: Icon(
                              Icons.add,
                              size: 18,
                              color: theme.colorScheme.onPrimaryContainer,
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
              ),
            );
          },
        );
      },
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => Center(child: Text('Error: $e')),
    );
  }
}

// ─── Inline Cart Panel (tablet side-by-side) ───

class _InlineCartPanel extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final cart = ref.watch(cartProvider);
    final theme = Theme.of(context);

    return Column(
      children: [
        // Header
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text('Cart', style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.bold)),
              if (cart.items.isNotEmpty)
                TextButton.icon(
                  onPressed: () async {
                    final confirmed = await showConfirmDialog(
                      context,
                      title: 'Clear Cart',
                      message: 'Remove all ${cart.itemCount} items?',
                      confirmLabel: 'Clear',
                      isDestructive: true,
                    );
                    if (confirmed) {
                      ref.read(cartProvider.notifier).clear();
                      HapticFeedback.mediumImpact();
                    }
                  },
                  icon: const Icon(Icons.delete_outline, size: 16),
                  label: const Text('Clear'),
                  style: TextButton.styleFrom(foregroundColor: theme.colorScheme.error),
                ),
            ],
          ),
        ),
        const Divider(height: 1),
        // Items
        Expanded(
          child: cart.items.isEmpty
              ? const EmptyState(
                  icon: Icons.shopping_cart_outlined,
                  title: 'Cart Empty',
                  subtitle: 'Tap items to add',
                )
              : ListView.builder(
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                  itemCount: cart.items.length,
                  itemBuilder: (context, index) {
                    final item = cart.items[index];
                    return Card(
                      margin: const EdgeInsets.symmetric(vertical: 3),
                      child: Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                        child: Row(
                          children: [
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(item.item.name,
                                      style: theme.textTheme.bodyMedium?.copyWith(fontWeight: FontWeight.w600),
                                      maxLines: 1, overflow: TextOverflow.ellipsis),
                                  Text('₱${item.unitPrice.toStringAsFixed(2)}',
                                      style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.outline)),
                                ],
                              ),
                            ),
                            Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                IconButton(
                                  icon: const Icon(Icons.remove, size: 16),
                                  constraints: const BoxConstraints(minWidth: 32, minHeight: 32),
                                  padding: EdgeInsets.zero,
                                  onPressed: () {
                                    ref.read(cartProvider.notifier).updateQty(index, item.qty - 1);
                                    HapticFeedback.selectionClick();
                                  },
                                ),
                                Text('${item.qty == item.qty.roundToDouble() ? item.qty.toInt() : item.qty}',
                                    style: theme.textTheme.bodyMedium?.copyWith(fontWeight: FontWeight.bold)),
                                IconButton(
                                  icon: const Icon(Icons.add, size: 16),
                                  constraints: const BoxConstraints(minWidth: 32, minHeight: 32),
                                  padding: EdgeInsets.zero,
                                  onPressed: () {
                                    ref.read(cartProvider.notifier).updateQty(index, item.qty + 1);
                                    HapticFeedback.selectionClick();
                                  },
                                ),
                              ],
                            ),
                            SizedBox(
                              width: 60,
                              child: Text('₱${item.lineTotal.toStringAsFixed(2)}',
                                  textAlign: TextAlign.end,
                                  style: theme.textTheme.bodyMedium?.copyWith(fontWeight: FontWeight.bold)),
                            ),
                          ],
                        ),
                      ),
                    );
                  },
                ),
        ),
        // Totals + pay
        if (cart.items.isNotEmpty)
          Container(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 12),
            decoration: BoxDecoration(
              border: Border(top: BorderSide(color: theme.colorScheme.outlineVariant)),
            ),
            child: SafeArea(
              child: Column(
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      const Text('Total'),
                      Text('₱${cart.total.toStringAsFixed(2)}',
                          style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.bold, color: theme.colorScheme.primary)),
                    ],
                  ),
                  const SizedBox(height: 8),
                  SizedBox(
                    width: double.infinity,
                    child: FilledButton.icon(
                      onPressed: () => _processPaymentInline(context, ref),
                      icon: const Icon(Icons.payment),
                      label: const Text('Pay Now'),
                    ),
                  ),
                ],
              ),
            ),
          ),
      ],
    );
  }

  Future<void> _processPaymentInline(BuildContext context, WidgetRef ref) async {
    final cart = ref.read(cartProvider);
    final userId = await ref.read(authServiceProvider).getCurrentUserId();
    if (userId == null) return;

    final result = await showPaymentDialog(context, total: cart.total);
    if (result == null) return;

    try {
      await ref.read(posRepositoryProvider).createSale(
            warehouseId: 1,
            locationId: 1,
            createdById: userId,
            subtotal: cart.subtotal,
            discountAmount: cart.totalDiscount,
            taxAmount: 0,
            total: cart.total,
            amountPaid: result.amountPaid,
            changeAmount: result.change,
            lines: cart.items
                .map((i) => {
                      'item_id': i.item.id,
                      'unit_id': i.unitId,
                      'qty': i.qty,
                      'unit_price': i.unitPrice,
                      'discount_amount': i.discountAmount,
                      'line_total': i.lineTotal,
                    })
                .toList(),
            payments: result.payments
                .map((p) => {
                      'method': p.methodCode,
                      'amount': p.amount,
                      if (p.reference != null) 'reference': p.reference,
                    })
                .toList(),
          );

      final receiptItems = cart.items
          .map((i) => ReceiptLineItem(
                name: i.item.name,
                qty: i.qty,
                unitPrice: i.unitPrice,
                lineTotal: i.lineTotal,
              ))
          .toList();

      ref.read(cartProvider.notifier).clear();
      HapticFeedback.heavyImpact();

      if (context.mounted) {
        await Navigator.of(context).push(
          MaterialPageRoute(
            builder: (_) => ReceiptScreen(
              saleId: DateTime.now().millisecondsSinceEpoch.toRadixString(16),
              dateTime: DateTime.now(),
              items: receiptItems,
              subtotal: cart.subtotal,
              discount: cart.totalDiscount,
              total: cart.total,
              payments: result.payments,
              amountPaid: result.amountPaid,
              change: result.change,
            ),
          ),
        );
      }
    } catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Error: $e'), backgroundColor: Colors.red),
        );
      }
    }
  }
}

// ─── Cart Bottom Sheet (phone) ───

class _CartSheet extends ConsumerWidget {
  const _CartSheet();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final cart = ref.watch(cartProvider);
    final theme = Theme.of(context);

    return DraggableScrollableSheet(
      initialChildSize: 0.85,
      maxChildSize: 0.95,
      minChildSize: 0.5,
      expand: false,
      builder: (context, scrollController) {
        return Column(
          children: [
            // Handle
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
                  Text('Cart', style: theme.textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.bold)),
                  if (cart.items.isNotEmpty)
                    TextButton.icon(
                      onPressed: () async {
                        final confirmed = await showConfirmDialog(
                          context,
                          title: 'Clear Cart',
                          message: 'Remove all ${cart.itemCount} items from cart?',
                          confirmLabel: 'Clear',
                          isDestructive: true,
                        );
                        if (confirmed) {
                          ref.read(cartProvider.notifier).clear();
                          HapticFeedback.mediumImpact();
                        }
                      },
                      icon: const Icon(Icons.delete_outline, size: 18),
                      label: const Text('Clear'),
                      style: TextButton.styleFrom(foregroundColor: theme.colorScheme.error),
                    ),
                ],
              ),
            ),
            Expanded(
              child: cart.items.isEmpty
                  ? const EmptyState(
                      icon: Icons.shopping_cart_outlined,
                      title: 'Your Cart is Empty',
                      subtitle: 'Tap items from the catalog to add them',
                    )
                  : ListView.builder(
                      controller: scrollController,
                      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                      itemCount: cart.items.length,
                      itemBuilder: (context, index) {
                        final item = cart.items[index];
                        return Dismissible(
                          key: ValueKey('${item.item.id}_${item.unitId}'),
                          direction: DismissDirection.endToStart,
                          background: Container(
                            alignment: Alignment.centerRight,
                            padding: const EdgeInsets.only(right: 20),
                            decoration: BoxDecoration(
                              color: Colors.red.withAlpha(30),
                              borderRadius: BorderRadius.circular(12),
                            ),
                            child: const Icon(Icons.delete_outline, color: Colors.red),
                          ),
                          onDismissed: (_) {
                            ref.read(cartProvider.notifier).removeItem(index);
                            HapticFeedback.mediumImpact();
                          },
                          child: Card(
                            margin: const EdgeInsets.symmetric(vertical: 4),
                            child: Padding(
                              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                              child: Row(
                                children: [
                                  // Item info
                                  Expanded(
                                    child: Column(
                                      crossAxisAlignment: CrossAxisAlignment.start,
                                      children: [
                                        Text(
                                          item.item.name,
                                          style: theme.textTheme.titleSmall?.copyWith(
                                            fontWeight: FontWeight.w600,
                                          ),
                                          maxLines: 1,
                                          overflow: TextOverflow.ellipsis,
                                        ),
                                        const SizedBox(height: 2),
                                        Text(
                                          '₱${item.unitPrice.toStringAsFixed(2)} each',
                                          style: theme.textTheme.bodySmall?.copyWith(
                                            color: theme.colorScheme.outline,
                                          ),
                                        ),
                                      ],
                                    ),
                                  ),
                                  // Quantity controls
                                  Container(
                                    decoration: BoxDecoration(
                                      color: theme.colorScheme.surfaceContainerHighest,
                                      borderRadius: BorderRadius.circular(10),
                                    ),
                                    child: Row(
                                      mainAxisSize: MainAxisSize.min,
                                      children: [
                                        IconButton(
                                          icon: const Icon(Icons.remove, size: 18),
                                          onPressed: () {
                                            ref.read(cartProvider.notifier)
                                                .updateQty(index, item.qty - 1);
                                            HapticFeedback.selectionClick();
                                          },
                                          constraints: const BoxConstraints(
                                            minWidth: 36,
                                            minHeight: 36,
                                          ),
                                          padding: EdgeInsets.zero,
                                        ),
                                        SizedBox(
                                          width: 36,
                                          child: Text(
                                            _formatQty(item.qty),
                                            textAlign: TextAlign.center,
                                            style: theme.textTheme.titleSmall?.copyWith(
                                              fontWeight: FontWeight.bold,
                                            ),
                                          ),
                                        ),
                                        IconButton(
                                          icon: const Icon(Icons.add, size: 18),
                                          onPressed: () {
                                            ref.read(cartProvider.notifier)
                                                .updateQty(index, item.qty + 1);
                                            HapticFeedback.selectionClick();
                                          },
                                          constraints: const BoxConstraints(
                                            minWidth: 36,
                                            minHeight: 36,
                                          ),
                                          padding: EdgeInsets.zero,
                                        ),
                                      ],
                                    ),
                                  ),
                                  const SizedBox(width: 12),
                                  // Line total
                                  SizedBox(
                                    width: 72,
                                    child: Text(
                                      '₱${item.lineTotal.toStringAsFixed(2)}',
                                      textAlign: TextAlign.end,
                                      style: theme.textTheme.titleSmall?.copyWith(
                                        fontWeight: FontWeight.bold,
                                      ),
                                    ),
                                  ),
                                ],
                              ),
                            ),
                          ),
                        );
                      },
                    ),
            ),
            if (cart.items.isNotEmpty)
              Container(
                padding: const EdgeInsets.fromLTRB(20, 12, 20, 12),
                decoration: BoxDecoration(
                  color: theme.colorScheme.surface,
                  border: Border(
                    top: BorderSide(color: theme.colorScheme.outlineVariant),
                  ),
                ),
                child: SafeArea(
                  child: Column(
                    children: [
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Text('Subtotal', style: theme.textTheme.bodyMedium),
                          Text('₱${cart.subtotal.toStringAsFixed(2)}',
                              style: theme.textTheme.bodyMedium),
                        ],
                      ),
                      if (cart.totalDiscount > 0) ...[
                        const SizedBox(height: 4),
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            Text('Discount',
                                style: TextStyle(color: Colors.green[600])),
                            Text('-₱${cart.totalDiscount.toStringAsFixed(2)}',
                                style: TextStyle(color: Colors.green[600])),
                          ],
                        ),
                      ],
                      const Divider(height: 16),
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Text('Total',
                              style: theme.textTheme.titleLarge?.copyWith(
                                fontWeight: FontWeight.bold,
                              )),
                          Text(
                            '₱${cart.total.toStringAsFixed(2)}',
                            style: theme.textTheme.titleLarge?.copyWith(
                              fontWeight: FontWeight.bold,
                              color: theme.colorScheme.primary,
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 12),
                      SizedBox(
                        width: double.infinity,
                        child: FilledButton.icon(
                          onPressed: () => _processPayment(context, ref),
                          icon: const Icon(Icons.payment),
                          label: const Text('Pay Now', style: TextStyle(fontSize: 16)),
                          style: FilledButton.styleFrom(
                            padding: const EdgeInsets.symmetric(vertical: 14),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
          ],
        );
      },
    );
  }

  String _formatQty(double qty) {
    return qty == qty.roundToDouble() ? qty.toInt().toString() : qty.toStringAsFixed(2);
  }

  Future<void> _processPayment(BuildContext context, WidgetRef ref) async {
    final cart = ref.read(cartProvider);
    final userId = await ref.read(authServiceProvider).getCurrentUserId();
    if (userId == null) return;

    // Show payment method dialog
    final result = await showPaymentDialog(context, total: cart.total);
    if (result == null) return; // User cancelled

    try {
      await ref.read(posRepositoryProvider).createSale(
            warehouseId: 1,
            locationId: 1,
            createdById: userId,
            subtotal: cart.subtotal,
            discountAmount: cart.totalDiscount,
            taxAmount: 0,
            total: cart.total,
            amountPaid: result.amountPaid,
            changeAmount: result.change,
            lines: cart.items
                .map((i) => {
                      'item_id': i.item.id,
                      'unit_id': i.unitId,
                      'qty': i.qty,
                      'unit_price': i.unitPrice,
                      'discount_amount': i.discountAmount,
                      'line_total': i.lineTotal,
                    })
                .toList(),
            payments: result.payments
                .map((p) => {
                      'method': p.methodCode,
                      'amount': p.amount,
                      if (p.reference != null) 'reference': p.reference,
                    })
                .toList(),
          );

      // Build receipt data
      final receiptItems = cart.items
          .map((i) => ReceiptLineItem(
                name: i.item.name,
                qty: i.qty,
                unitPrice: i.unitPrice,
                lineTotal: i.lineTotal,
              ))
          .toList();

      ref.read(cartProvider.notifier).clear();
      HapticFeedback.heavyImpact();

      if (context.mounted) {
        Navigator.of(context).pop(); // Close cart sheet

        // Show receipt
        await Navigator.of(context).push(
          MaterialPageRoute(
            builder: (_) => ReceiptScreen(
              saleId: DateTime.now().millisecondsSinceEpoch.toRadixString(16),
              dateTime: DateTime.now(),
              items: receiptItems,
              subtotal: cart.subtotal,
              discount: cart.totalDiscount,
              total: cart.total,
              payments: result.payments,
              amountPaid: result.amountPaid,
              change: result.change,
            ),
          ),
        );
      }
    } catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Error processing sale: $e'),
            backgroundColor: Colors.red,
          ),
        );
      }
    }
  }
}
