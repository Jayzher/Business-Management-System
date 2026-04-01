import 'package:flutter/material.dart';

class ShimmerLoading extends StatefulWidget {
  final int itemCount;
  final ShimmerStyle style;

  const ShimmerLoading({
    super.key,
    this.itemCount = 5,
    this.style = ShimmerStyle.list,
  });

  @override
  State<ShimmerLoading> createState() => _ShimmerLoadingState();
}

enum ShimmerStyle { list, grid, card }

class _ShimmerLoadingState extends State<ShimmerLoading>
    with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  late Animation<double> _animation;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1200),
    )..repeat();
    _animation = Tween<double>(begin: -1.0, end: 2.0).animate(
      CurvedAnimation(parent: _controller, curve: Curves.easeInOut),
    );
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final baseColor = isDark ? Colors.grey[800]! : Colors.grey[300]!;
    final highlightColor = isDark ? Colors.grey[700]! : Colors.grey[100]!;

    return AnimatedBuilder(
      animation: _animation,
      builder: (context, _) {
        return switch (widget.style) {
          ShimmerStyle.list => _buildListShimmer(baseColor, highlightColor),
          ShimmerStyle.grid => _buildGridShimmer(baseColor, highlightColor),
          ShimmerStyle.card => _buildCardShimmer(baseColor, highlightColor),
        };
      },
    );
  }

  Widget _buildListShimmer(Color base, Color highlight) {
    return ListView.builder(
      physics: const NeverScrollableScrollPhysics(),
      itemCount: widget.itemCount,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      itemBuilder: (_, __) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 6),
        child: Row(
          children: [
            _shimmerBox(base, highlight, width: 48, height: 48, circular: true),
            const SizedBox(width: 16),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _shimmerBox(base, highlight, width: double.infinity, height: 14),
                  const SizedBox(height: 8),
                  _shimmerBox(base, highlight, width: 150, height: 10),
                ],
              ),
            ),
            const SizedBox(width: 16),
            _shimmerBox(base, highlight, width: 60, height: 14),
          ],
        ),
      ),
    );
  }

  Widget _buildGridShimmer(Color base, Color highlight) {
    return GridView.builder(
      physics: const NeverScrollableScrollPhysics(),
      padding: const EdgeInsets.all(16),
      gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount: 2,
        childAspectRatio: 1.2,
        crossAxisSpacing: 12,
        mainAxisSpacing: 12,
      ),
      itemCount: widget.itemCount,
      itemBuilder: (_, __) => Card(
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _shimmerBox(base, highlight, width: 60, height: 10),
              const SizedBox(height: 8),
              _shimmerBox(base, highlight, width: double.infinity, height: 14),
              const Spacer(),
              _shimmerBox(base, highlight, width: 80, height: 16),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildCardShimmer(Color base, Color highlight) {
    return ListView.builder(
      physics: const NeverScrollableScrollPhysics(),
      padding: const EdgeInsets.all(16),
      itemCount: widget.itemCount,
      itemBuilder: (_, __) => Card(
        margin: const EdgeInsets.only(bottom: 12),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _shimmerBox(base, highlight, width: double.infinity, height: 16),
              const SizedBox(height: 12),
              _shimmerBox(base, highlight, width: 200, height: 12),
              const SizedBox(height: 8),
              _shimmerBox(base, highlight, width: 150, height: 12),
            ],
          ),
        ),
      ),
    );
  }

  Widget _shimmerBox(Color base, Color highlight,
      {required double height, double? width, bool circular = false}) {
    return Container(
      width: width,
      height: height,
      decoration: BoxDecoration(
        borderRadius: circular ? null : BorderRadius.circular(4),
        shape: circular ? BoxShape.circle : BoxShape.rectangle,
        gradient: LinearGradient(
          begin: Alignment.centerLeft,
          end: Alignment.centerRight,
          colors: [base, highlight, base],
          stops: [
            (_animation.value - 0.3).clamp(0.0, 1.0),
            _animation.value.clamp(0.0, 1.0),
            (_animation.value + 0.3).clamp(0.0, 1.0),
          ],
        ),
      ),
    );
  }
}
