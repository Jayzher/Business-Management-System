import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../utils/responsive.dart';

class PartnerDetailScreen extends StatelessWidget {
  final String type; // 'customer' or 'supplier'
  final String name;
  final String code;
  final String? phone;
  final String? email;
  final String? address;
  final String? city;
  final String? taxId;
  final String? contactPerson;
  final String? notes;

  const PartnerDetailScreen({
    super.key,
    required this.type,
    required this.name,
    required this.code,
    this.phone,
    this.email,
    this.address,
    this.city,
    this.taxId,
    this.contactPerson,
    this.notes,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isCustomer = type == 'customer';

    return Scaffold(
      appBar: AppBar(
        title: Text(name),
      ),
      body: ResponsiveCenter(
        child: ListView(
        padding: Responsive.bodyPadding(context),
        children: [
          // Header card
          Card(
            child: Padding(
              padding: const EdgeInsets.all(20),
              child: Column(
                children: [
                  CircleAvatar(
                    radius: 36,
                    backgroundColor: isCustomer
                        ? Colors.purple.withAlpha(30)
                        : Colors.blue.withAlpha(30),
                    child: Text(
                      _initials(name),
                      style: theme.textTheme.headlineSmall?.copyWith(
                        color: isCustomer ? Colors.purple : Colors.blue,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ),
                  const SizedBox(height: 12),
                  Text(name, style: theme.textTheme.titleLarge),
                  const SizedBox(height: 4),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                    decoration: BoxDecoration(
                      color: theme.colorScheme.surfaceContainerHighest,
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Text(
                      code,
                      style: theme.textTheme.labelMedium?.copyWith(
                        fontFamily: 'monospace',
                      ),
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    isCustomer ? 'Customer' : 'Supplier',
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: theme.colorScheme.outline,
                    ),
                  ),
                ],
              ),
            ),
          ),

          const SizedBox(height: 16),

          // Quick actions
          if ((phone != null && phone!.isNotEmpty) || (email != null && email!.isNotEmpty))
            Card(
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                  children: [
                    if (phone != null && phone!.isNotEmpty)
                      _QuickAction(
                        icon: Icons.phone_outlined,
                        label: 'Call',
                        onTap: () {
                          HapticFeedback.lightImpact();
                          ScaffoldMessenger.of(context).showSnackBar(
                            SnackBar(content: Text('Calling $phone...')),
                          );
                        },
                      ),
                    if (phone != null && phone!.isNotEmpty)
                      _QuickAction(
                        icon: Icons.message_outlined,
                        label: 'Message',
                        onTap: () {
                          HapticFeedback.lightImpact();
                          ScaffoldMessenger.of(context).showSnackBar(
                            SnackBar(content: Text('Messaging $phone...')),
                          );
                        },
                      ),
                    if (email != null && email!.isNotEmpty)
                      _QuickAction(
                        icon: Icons.email_outlined,
                        label: 'Email',
                        onTap: () {
                          HapticFeedback.lightImpact();
                          ScaffoldMessenger.of(context).showSnackBar(
                            SnackBar(content: Text('Emailing $email...')),
                          );
                        },
                      ),
                  ],
                ),
              ),
            ),

          const SizedBox(height: 16),

          // Details
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Details', style: theme.textTheme.titleMedium),
                  const SizedBox(height: 12),
                  if (contactPerson != null && contactPerson!.isNotEmpty)
                    _DetailRow(icon: Icons.person_outline, label: 'Contact', value: contactPerson!),
                  if (phone != null && phone!.isNotEmpty)
                    _DetailRow(icon: Icons.phone_outlined, label: 'Phone', value: phone!),
                  if (email != null && email!.isNotEmpty)
                    _DetailRow(icon: Icons.email_outlined, label: 'Email', value: email!),
                  if (address != null && address!.isNotEmpty)
                    _DetailRow(icon: Icons.location_on_outlined, label: 'Address', value: address!),
                  if (city != null && city!.isNotEmpty)
                    _DetailRow(icon: Icons.location_city_outlined, label: 'City', value: city!),
                  if (taxId != null && taxId!.isNotEmpty)
                    _DetailRow(icon: Icons.receipt_outlined, label: 'Tax ID', value: taxId!),
                ],
              ),
            ),
          ),

          if (notes != null && notes!.isNotEmpty) ...[
            const SizedBox(height: 16),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('Notes', style: theme.textTheme.titleMedium),
                    const SizedBox(height: 8),
                    Text(notes!, style: theme.textTheme.bodyMedium),
                  ],
                ),
              ),
            ),
          ],
        ],
      ),
      ),
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

class _QuickAction extends StatelessWidget {
  final IconData icon;
  final String label;
  final VoidCallback onTap;

  const _QuickAction({
    required this.icon,
    required this.label,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return InkWell(
      borderRadius: BorderRadius.circular(12),
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, color: theme.colorScheme.primary),
            const SizedBox(height: 4),
            Text(label, style: theme.textTheme.labelSmall),
          ],
        ),
      ),
    );
  }
}

class _DetailRow extends StatelessWidget {
  final IconData icon;
  final String label;
  final String value;

  const _DetailRow({
    required this.icon,
    required this.label,
    required this.value,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, size: 20, color: theme.colorScheme.outline),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(label, style: theme.textTheme.labelSmall?.copyWith(color: theme.colorScheme.outline)),
                const SizedBox(height: 2),
                Text(value, style: theme.textTheme.bodyMedium),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
