import 'package:flutter/material.dart';

/// Responsive breakpoints following Material 3 adaptive layout guidelines.
/// - compact: phones in portrait (< 600dp)
/// - medium: small tablets, foldables, phones in landscape (600–840dp)
/// - expanded: large tablets, desktops (> 840dp)
enum ScreenSize { compact, medium, expanded }

class Responsive {
  Responsive._();

  static const double compactBreakpoint = 600;
  static const double expandedBreakpoint = 840;

  /// Return the current [ScreenSize] based on widget width.
  static ScreenSize screenSize(BuildContext context) {
    final width = MediaQuery.sizeOf(context).width;
    if (width >= expandedBreakpoint) return ScreenSize.expanded;
    if (width >= compactBreakpoint) return ScreenSize.medium;
    return ScreenSize.compact;
  }

  static double width(BuildContext context) => MediaQuery.sizeOf(context).width;
  static double height(BuildContext context) => MediaQuery.sizeOf(context).height;

  /// Pick a value per breakpoint. Falls back in order: expanded → medium → compact.
  static T value<T>(
    BuildContext context, {
    required T compact,
    T? medium,
    T? expanded,
  }) {
    switch (screenSize(context)) {
      case ScreenSize.expanded:
        return expanded ?? medium ?? compact;
      case ScreenSize.medium:
        return medium ?? compact;
      case ScreenSize.compact:
        return compact;
    }
  }

  /// Horizontal padding that grows with screen size.
  static EdgeInsets horizontalPadding(BuildContext context) {
    return EdgeInsets.symmetric(
      horizontal: value(context, compact: 16.0, medium: 24.0, expanded: 32.0),
    );
  }

  /// Scaffold body padding that grows with screen size.
  static EdgeInsets bodyPadding(BuildContext context) {
    return EdgeInsets.symmetric(
      horizontal: value(context, compact: 16.0, medium: 24.0, expanded: 32.0),
      vertical: value(context, compact: 8.0, medium: 12.0, expanded: 16.0),
    );
  }

  /// Grid cross-axis count for item grids.
  static int gridColumns(BuildContext context, {int compact = 2, int medium = 3, int expanded = 4}) {
    return value(context, compact: compact, medium: medium, expanded: expanded);
  }

  /// Maximum content width — constrains content on very wide screens.
  static double maxContentWidth(BuildContext context) {
    return value<double>(context, compact: double.infinity, medium: 720, expanded: 960);
  }

  /// Whether to show a rail (side nav) instead of bottom nav.
  static bool useNavigationRail(BuildContext context) {
    return screenSize(context) != ScreenSize.compact;
  }

  /// Whether to show side-by-side layout (e.g. POS: catalog + cart).
  static bool useSideBySide(BuildContext context) {
    return screenSize(context) != ScreenSize.compact;
  }
}

/// Wrapper that constrains child to [Responsive.maxContentWidth] and centers it.
class ResponsiveCenter extends StatelessWidget {
  final Widget child;
  final EdgeInsetsGeometry? padding;

  const ResponsiveCenter({super.key, required this.child, this.padding});

  @override
  Widget build(BuildContext context) {
    final maxWidth = Responsive.maxContentWidth(context);
    return Center(
      child: ConstrainedBox(
        constraints: BoxConstraints(maxWidth: maxWidth),
        child: padding != null ? Padding(padding: padding!, child: child) : child,
      ),
    );
  }
}
