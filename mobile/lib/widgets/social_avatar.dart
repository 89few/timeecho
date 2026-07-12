import 'package:flutter/material.dart';

import '../core/app_config.dart';
import '../core/theme.dart';

class SocialAvatar extends StatelessWidget {
  const SocialAvatar({
    super.key,
    required this.name,
    this.url,
    this.radius = 22,
    this.heroTag,
  });

  final String name;
  final String? url;
  final double radius;
  final Object? heroTag;

  String? get _resolvedUrl {
    final value = url?.trim();
    if (value == null || value.isEmpty) return null;
    if (value.startsWith('http://') || value.startsWith('https://')) {
      return value;
    }
    return '${AppConfig.apiBaseUrl}${value.startsWith('/') ? '' : '/'}$value';
  }

  @override
  Widget build(BuildContext context) {
    final resolved = _resolvedUrl;
    const palette = [
      TimeEchoColors.duskPurple,
      TimeEchoColors.mossGreen,
      Color(0xFFB47A62),
      Color(0xFF6587A3),
      Color(0xFF9A718F),
    ];
    final color = palette[
        name.codeUnits.fold<int>(0, (sum, item) => sum + item) %
            palette.length];
    final fallback = CircleAvatar(
      radius: radius,
      backgroundColor: color.withValues(alpha: .14),
      child: Icon(Icons.person_rounded, size: radius * 1.08, color: color),
    );
    final avatar = resolved == null
        ? fallback
        : CircleAvatar(
            radius: radius,
            backgroundColor: color.withValues(alpha: .12),
            child: ClipOval(
              child: Image.network(
                resolved,
                width: radius * 2,
                height: radius * 2,
                fit: BoxFit.cover,
                cacheWidth: (radius * 4).round(),
                errorBuilder: (_, __, ___) => fallback,
              ),
            ),
          );
    if (heroTag == null) return avatar;
    return Hero(tag: heroTag!, child: avatar);
  }
}
