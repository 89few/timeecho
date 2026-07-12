import 'package:flutter/material.dart';

class TimeEchoCard extends StatelessWidget {
  const TimeEchoCard({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.all(18),
    this.onTap,
  });

  final Widget child;
  final EdgeInsetsGeometry padding;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final radius = BorderRadius.circular(24);
    final content = Padding(padding: padding, child: child);
    return SizedBox(
      width: double.infinity,
      child: Material(
        color: Theme.of(context).colorScheme.surface,
        borderRadius: radius,
        elevation: 2,
        shadowColor: Colors.black.withValues(alpha: .12),
        clipBehavior: Clip.antiAlias,
        child: onTap == null
            ? content
            : InkWell(borderRadius: radius, onTap: onTap, child: content),
      ),
    );
  }
}
