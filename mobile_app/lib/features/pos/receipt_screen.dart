import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'payment_dialog.dart';

class ReceiptScreen extends StatelessWidget {
  final String saleId;
  final DateTime dateTime;
  final List<ReceiptLineItem> items;
  final double subtotal;
  final double discount;
  final double total;
  final List<PaymentEntry> payments;
  final double amountPaid;
  final double change;
  final String? customerName;

  const ReceiptScreen({
    super.key,
    required this.saleId,
    required this.dateTime,
    required this.items,
    required this.subtotal,
    required this.discount,
    required this.total,
    required this.payments,
    required this.amountPaid,
    required this.change,
    this.customerName,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Receipt'),
        leading: IconButton(
          icon: const Icon(Icons.close),
          onPressed: () => Navigator.of(context).pop(),
        ),
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(20),
        child: Column(
          children: [
            // Success indicator
            Container(
              width: 72,
              height: 72,
              decoration: BoxDecoration(
                color: Colors.green.withAlpha(30),
                shape: BoxShape.circle,
              ),
              child: const Icon(Icons.check_circle, color: Colors.green, size: 48),
            ),
            const SizedBox(height: 12),
            Text('Payment Complete!', style: theme.textTheme.headlineSmall),
            const SizedBox(height: 4),
            Text(
              _formatDate(dateTime),
              style: theme.textTheme.bodyMedium?.copyWith(
                color: theme.colorScheme.outline,
              ),
            ),
            const SizedBox(height: 24),

            // Receipt card
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    // Sale ID
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Text('Transaction', style: theme.textTheme.labelMedium),
                        Text(
                          '#${saleId.substring(0, 8).toUpperCase()}',
                          style: theme.textTheme.labelMedium?.copyWith(
                            fontFamily: 'monospace',
                          ),
                        ),
                      ],
                    ),
                    if (customerName != null) ...[
                      const SizedBox(height: 4),
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Text('Customer', style: theme.textTheme.labelMedium),
                          Text(customerName!),
                        ],
                      ),
                    ],

                    const Divider(height: 24),

                    // Line items
                    ...items.map((item) => Padding(
                          padding: const EdgeInsets.symmetric(vertical: 4),
                          child: Row(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Expanded(
                                flex: 3,
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Text(item.name, style: theme.textTheme.bodyMedium),
                                    Text(
                                      '${_formatQty(item.qty)} × ₱${item.unitPrice.toStringAsFixed(2)}',
                                      style: theme.textTheme.bodySmall?.copyWith(
                                        color: theme.colorScheme.outline,
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                              Text(
                                '₱${item.lineTotal.toStringAsFixed(2)}',
                                style: theme.textTheme.bodyMedium?.copyWith(
                                  fontWeight: FontWeight.w500,
                                ),
                              ),
                            ],
                          ),
                        )),

                    const Divider(height: 24),

                    // Totals
                    _TotalRow(label: 'Subtotal', value: '₱${subtotal.toStringAsFixed(2)}'),
                    if (discount > 0)
                      _TotalRow(
                        label: 'Discount',
                        value: '-₱${discount.toStringAsFixed(2)}',
                        valueColor: Colors.green,
                      ),
                    const SizedBox(height: 8),
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Text('Total', style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.bold)),
                        Text('₱${total.toStringAsFixed(2)}',
                            style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.bold)),
                      ],
                    ),

                    const Divider(height: 24),

                    // Payments
                    Text('Payments', style: theme.textTheme.labelMedium),
                    const SizedBox(height: 8),
                    ...payments.map((p) => Padding(
                          padding: const EdgeInsets.symmetric(vertical: 2),
                          child: Row(
                            children: [
                              Icon(p.methodIcon, size: 16, color: theme.colorScheme.outline),
                              const SizedBox(width: 8),
                              Expanded(child: Text(p.methodLabel)),
                              Text('₱${p.amount.toStringAsFixed(2)}'),
                            ],
                          ),
                        )),

                    if (change > 0) ...[
                      const SizedBox(height: 8),
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Text('Change', style: TextStyle(color: Colors.green[700])),
                          Text(
                            '₱${change.toStringAsFixed(2)}',
                            style: TextStyle(
                              color: Colors.green[700],
                              fontWeight: FontWeight.bold,
                            ),
                          ),
                        ],
                      ),
                    ],
                  ],
                ),
              ),
            ),

            const SizedBox(height: 24),

            // Actions
            Row(
              children: [
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: () {
                      HapticFeedback.lightImpact();
                      ScaffoldMessenger.of(context).showSnackBar(
                        const SnackBar(content: Text('Receipt copied to clipboard')),
                      );
                    },
                    icon: const Icon(Icons.copy, size: 18),
                    label: const Text('Copy'),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: FilledButton.icon(
                    onPressed: () => Navigator.of(context).pop(),
                    icon: const Icon(Icons.receipt_long, size: 18),
                    label: const Text('Done'),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  String _formatDate(DateTime dt) {
    final months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    return '${months[dt.month - 1]} ${dt.day}, ${dt.year} ${dt.hour.toString().padLeft(2, '0')}:${dt.minute.toString().padLeft(2, '0')}';
  }

  String _formatQty(double qty) {
    return qty == qty.roundToDouble() ? qty.toInt().toString() : qty.toStringAsFixed(2);
  }
}

class ReceiptLineItem {
  final String name;
  final double qty;
  final double unitPrice;
  final double lineTotal;

  const ReceiptLineItem({
    required this.name,
    required this.qty,
    required this.unitPrice,
    required this.lineTotal,
  });
}

class _TotalRow extends StatelessWidget {
  final String label;
  final String value;
  final Color? valueColor;

  const _TotalRow({required this.label, required this.value, this.valueColor});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label, style: Theme.of(context).textTheme.bodyMedium),
          Text(value,
              style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                    color: valueColor,
                  )),
        ],
      ),
    );
  }
}
