import 'package:flutter/material.dart';

import '../core/constants.dart';
import '../core/theme.dart';

class StateBadge extends StatelessWidget {
  const StateBadge({super.key, required this.status});

  final String status;

  @override
  Widget build(BuildContext context) {
    final label = statusLabels[status] ?? status;
    final color = switch (status) {
      'SEALED' => TimeEchoColors.duskPurple,
      'AVAILABLE' => TimeEchoColors.mossGreen,
      'SALVAGED' => TimeEchoColors.warmApricot,
      'RISK_REVIEW' => Colors.orange,
      'DESTROYED' => TimeEchoColors.muted,
      _ => TimeEchoColors.muted,
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: color.withValues(alpha: .14),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        label,
        style: TextStyle(
          color: color,
          fontWeight: FontWeight.w700,
          fontSize: 12,
        ),
      ),
    );
  }
}
