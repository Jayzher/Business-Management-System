import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

enum PaymentMethod { cash, gcash, card, bankTransfer }

class PaymentEntry {
  final PaymentMethod method;
  final double amount;
  final String? reference;

  const PaymentEntry({
    required this.method,
    required this.amount,
    this.reference,
  });

  String get methodCode => switch (method) {
        PaymentMethod.cash => 'CASH',
        PaymentMethod.gcash => 'GCASH',
        PaymentMethod.card => 'CARD',
        PaymentMethod.bankTransfer => 'BANK_TRANSFER',
      };

  String get methodLabel => switch (method) {
        PaymentMethod.cash => 'Cash',
        PaymentMethod.gcash => 'GCash',
        PaymentMethod.card => 'Card',
        PaymentMethod.bankTransfer => 'Bank Transfer',
      };

  IconData get methodIcon => switch (method) {
        PaymentMethod.cash => Icons.payments_outlined,
        PaymentMethod.gcash => Icons.phone_android,
        PaymentMethod.card => Icons.credit_card,
        PaymentMethod.bankTransfer => Icons.account_balance,
      };
}

class PaymentResult {
  final List<PaymentEntry> payments;
  final double amountPaid;
  final double change;

  const PaymentResult({
    required this.payments,
    required this.amountPaid,
    required this.change,
  });
}

Future<PaymentResult?> showPaymentDialog(
  BuildContext context, {
  required double total,
}) {
  return showModalBottomSheet<PaymentResult>(
    context: context,
    isScrollControlled: true,
    useSafeArea: true,
    builder: (_) => _PaymentSheet(total: total),
  );
}

class _PaymentSheet extends StatefulWidget {
  final double total;
  const _PaymentSheet({required this.total});

  @override
  State<_PaymentSheet> createState() => _PaymentSheetState();
}

class _PaymentSheetState extends State<_PaymentSheet> {
  PaymentMethod _selectedMethod = PaymentMethod.cash;
  final _amountController = TextEditingController();
  final _referenceController = TextEditingController();
  final List<PaymentEntry> _payments = [];
  bool _showCustomAmount = false;

  double get _totalPaid =>
      _payments.fold(0.0, (sum, p) => sum + p.amount);

  double get _remaining => widget.total - _totalPaid;

  @override
  void initState() {
    super.initState();
    _amountController.text = widget.total.toStringAsFixed(2);
  }

  @override
  void dispose() {
    _amountController.dispose();
    _referenceController.dispose();
    super.dispose();
  }

  void _addPayment() {
    final amount = double.tryParse(_amountController.text) ?? 0;
    if (amount <= 0) return;

    final needsReference = _selectedMethod != PaymentMethod.cash;
    if (needsReference && _referenceController.text.trim().isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Please enter a reference number')),
      );
      return;
    }

    setState(() {
      _payments.add(PaymentEntry(
        method: _selectedMethod,
        amount: amount,
        reference: needsReference ? _referenceController.text.trim() : null,
      ));
      _referenceController.clear();
      _amountController.text = _remaining > 0 ? _remaining.toStringAsFixed(2) : '0.00';
      _showCustomAmount = false;
    });
    HapticFeedback.mediumImpact();
  }

  void _removePayment(int index) {
    setState(() {
      _payments.removeAt(index);
      if (_remaining > 0) {
        _amountController.text = _remaining.toStringAsFixed(2);
      }
    });
  }

  void _processPayment() {
    if (_payments.isEmpty) {
      // Quick pay: use current method and total
      final amount = double.tryParse(_amountController.text) ?? 0;
      if (amount < widget.total) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Amount is less than the total')),
        );
        return;
      }
      Navigator.of(context).pop(PaymentResult(
        payments: [
          PaymentEntry(method: _selectedMethod, amount: amount),
        ],
        amountPaid: amount,
        change: amount - widget.total,
      ));
    } else {
      if (_totalPaid < widget.total) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Still ₱${_remaining.toStringAsFixed(2)} remaining'),
          ),
        );
        return;
      }
      Navigator.of(context).pop(PaymentResult(
        payments: _payments,
        amountPaid: _totalPaid,
        change: _totalPaid - widget.total,
      ));
    }
    HapticFeedback.heavyImpact();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final change = _totalPaid > widget.total ? _totalPaid - widget.total : 0.0;

    return DraggableScrollableSheet(
      initialChildSize: 0.85,
      maxChildSize: 0.95,
      minChildSize: 0.5,
      expand: false,
      builder: (context, scrollController) {
        return Padding(
          padding: EdgeInsets.only(
            bottom: MediaQuery.of(context).viewInsets.bottom,
          ),
          child: Column(
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

              // Header
              Padding(
                padding: const EdgeInsets.fromLTRB(20, 16, 20, 8),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text('Payment', style: theme.textTheme.headlineSmall),
                    Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 16, vertical: 8),
                      decoration: BoxDecoration(
                        color: theme.colorScheme.primaryContainer,
                        borderRadius: BorderRadius.circular(20),
                      ),
                      child: Text(
                        '₱${widget.total.toStringAsFixed(2)}',
                        style: theme.textTheme.titleMedium?.copyWith(
                          fontWeight: FontWeight.bold,
                          color: theme.colorScheme.onPrimaryContainer,
                        ),
                      ),
                    ),
                  ],
                ),
              ),

              Expanded(
                child: ListView(
                  controller: scrollController,
                  padding: const EdgeInsets.symmetric(horizontal: 20),
                  children: [
                    // Payment method selector
                    const SizedBox(height: 8),
                    Text('Payment Method',
                        style: theme.textTheme.labelLarge
                            ?.copyWith(color: theme.colorScheme.outline)),
                    const SizedBox(height: 8),
                    Wrap(
                      spacing: 8,
                      runSpacing: 8,
                      children: PaymentMethod.values.map((method) {
                        final entry = PaymentEntry(method: method, amount: 0);
                        final selected = _selectedMethod == method;
                        return ChoiceChip(
                          avatar: Icon(entry.methodIcon, size: 18),
                          label: Text(entry.methodLabel),
                          selected: selected,
                          onSelected: (_) =>
                              setState(() => _selectedMethod = method),
                        );
                      }).toList(),
                    ),

                    // Quick amounts for cash
                    if (_selectedMethod == PaymentMethod.cash) ...[
                      const SizedBox(height: 16),
                      Text('Quick Amount',
                          style: theme.textTheme.labelLarge
                              ?.copyWith(color: theme.colorScheme.outline)),
                      const SizedBox(height: 8),
                      Wrap(
                        spacing: 8,
                        runSpacing: 8,
                        children: [
                          _QuickAmountChip(
                            label: 'Exact',
                            onTap: () {
                              setState(() {
                                _amountController.text =
                                    widget.total.toStringAsFixed(2);
                                _showCustomAmount = false;
                              });
                            },
                          ),
                          ..._suggestedAmounts().map(
                            (amount) => _QuickAmountChip(
                              label: '₱${amount.toStringAsFixed(0)}',
                              onTap: () {
                                setState(() {
                                  _amountController.text =
                                      amount.toStringAsFixed(2);
                                  _showCustomAmount = false;
                                });
                              },
                            ),
                          ),
                          _QuickAmountChip(
                            label: 'Custom',
                            onTap: () =>
                                setState(() => _showCustomAmount = true),
                          ),
                        ],
                      ),
                    ],

                    // Amount input
                    const SizedBox(height: 16),
                    if (_showCustomAmount ||
                        _selectedMethod != PaymentMethod.cash) ...[
                      TextField(
                        controller: _amountController,
                        keyboardType: const TextInputType.numberWithOptions(
                            decimal: true),
                        decoration: InputDecoration(
                          labelText: 'Amount',
                          prefixText: '₱ ',
                          border: OutlineInputBorder(
                            borderRadius: BorderRadius.circular(12),
                          ),
                        ),
                        inputFormatters: [
                          FilteringTextInputFormatter.allow(
                              RegExp(r'^\d*\.?\d{0,2}')),
                        ],
                        autofocus: true,
                      ),
                    ],

                    // Reference number for non-cash
                    if (_selectedMethod != PaymentMethod.cash) ...[
                      const SizedBox(height: 12),
                      TextField(
                        controller: _referenceController,
                        decoration: InputDecoration(
                          labelText: 'Reference Number',
                          hintText: switch (_selectedMethod) {
                            PaymentMethod.gcash => 'GCash ref #',
                            PaymentMethod.card => 'Card approval #',
                            PaymentMethod.bankTransfer =>
                              'Bank transaction ref #',
                            _ => 'Reference',
                          },
                          border: OutlineInputBorder(
                            borderRadius: BorderRadius.circular(12),
                          ),
                        ),
                      ),
                    ],

                    // Split payment button
                    if (_payments.isEmpty) ...[
                      const SizedBox(height: 12),
                      OutlinedButton.icon(
                        onPressed: _addPayment,
                        icon: const Icon(Icons.call_split, size: 18),
                        label: const Text('Split Payment'),
                      ),
                    ] else ...[
                      const SizedBox(height: 12),
                      FilledButton.tonal(
                        onPressed: _addPayment,
                        child: const Text('Add This Payment'),
                      ),
                    ],

                    // Payment entries
                    if (_payments.isNotEmpty) ...[
                      const SizedBox(height: 16),
                      Text('Payments Applied',
                          style: theme.textTheme.labelLarge
                              ?.copyWith(color: theme.colorScheme.outline)),
                      const SizedBox(height: 8),
                      ..._payments.asMap().entries.map((e) {
                        final p = e.value;
                        return Card(
                          child: ListTile(
                            leading: Icon(p.methodIcon),
                            title: Text(p.methodLabel),
                            subtitle: p.reference != null
                                ? Text('Ref: ${p.reference}')
                                : null,
                            trailing: Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Text(
                                  '₱${p.amount.toStringAsFixed(2)}',
                                  style:
                                      const TextStyle(fontWeight: FontWeight.bold),
                                ),
                                IconButton(
                                  icon: const Icon(Icons.close, size: 18),
                                  onPressed: () => _removePayment(e.key),
                                ),
                              ],
                            ),
                          ),
                        );
                      }),
                      if (_remaining > 0)
                        Padding(
                          padding: const EdgeInsets.only(top: 8),
                          child: Text(
                            'Remaining: ₱${_remaining.toStringAsFixed(2)}',
                            style: TextStyle(
                                color: theme.colorScheme.error,
                                fontWeight: FontWeight.w600),
                          ),
                        ),
                    ],

                    const SizedBox(height: 24),
                  ],
                ),
              ),

              // Bottom bar
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
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      if (change > 0 || (_payments.isNotEmpty && _totalPaid > widget.total))
                        Padding(
                          padding: const EdgeInsets.only(bottom: 8),
                          child: Row(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              const Icon(Icons.change_circle_outlined,
                                  color: Colors.green),
                              const SizedBox(width: 8),
                              Text(
                                'Change: ₱${(_payments.isNotEmpty ? _totalPaid - widget.total : (double.tryParse(_amountController.text) ?? 0) - widget.total).toStringAsFixed(2)}',
                                style: theme.textTheme.titleMedium?.copyWith(
                                  color: Colors.green[700],
                                  fontWeight: FontWeight.bold,
                                ),
                              ),
                            ],
                          ),
                        ),
                      SizedBox(
                        width: double.infinity,
                        child: FilledButton.icon(
                          onPressed: _processPayment,
                          icon: const Icon(Icons.check_circle_outline),
                          label: Text(
                            _payments.isEmpty
                                ? 'Pay ₱${widget.total.toStringAsFixed(2)}'
                                : 'Complete Payment',
                            style: const TextStyle(fontSize: 16),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ),
        );
      },
    );
  }

  List<double> _suggestedAmounts() {
    final total = widget.total;
    final suggestions = <double>{};

    // Round up to nearest 10, 50, 100, 500, 1000
    for (final mult in [10.0, 20.0, 50.0, 100.0, 500.0, 1000.0]) {
      final rounded = (total / mult).ceil() * mult;
      if (rounded > total && rounded <= total * 3) {
        suggestions.add(rounded.toDouble());
      }
    }

    return suggestions.toList()..sort();
  }
}

class _QuickAmountChip extends StatelessWidget {
  final String label;
  final VoidCallback onTap;

  const _QuickAmountChip({required this.label, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return ActionChip(
      label: Text(label),
      onPressed: onTap,
    );
  }
}
