import 'package:flutter/material.dart';

class TimeEchoColors {
  static const background = Color(0xFFF7F3EA);
  static const surface = Color(0xFFFFFDF8);
  static const ink = Color(0xFF243047);
  static const muted = Color(0xFF7B8190);
  static const mistBlue = Color(0xFFDDEAF3);
  static const duskPurple = Color(0xFF6D5B8C);
  static const warmApricot = Color(0xFFF4CDA5);
  static const mossGreen = Color(0xFF8BAA9A);
  static const dangerSoft = Color(0xFFE9A6A6);
}

ThemeData buildTheme() {
  final colorScheme = ColorScheme.fromSeed(
    seedColor: TimeEchoColors.duskPurple,
    brightness: Brightness.light,
    surface: TimeEchoColors.surface,
    primary: TimeEchoColors.duskPurple,
    secondary: TimeEchoColors.mossGreen,
    error: TimeEchoColors.dangerSoft,
  );

  return ThemeData(
    useMaterial3: true,
    colorScheme: colorScheme,
    scaffoldBackgroundColor: TimeEchoColors.background,
    fontFamily: 'Roboto',
    appBarTheme: const AppBarTheme(
      backgroundColor: TimeEchoColors.background,
      elevation: 0,
      centerTitle: false,
      foregroundColor: TimeEchoColors.ink,
    ),
    cardTheme: CardThemeData(
      elevation: 0,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
      color: TimeEchoColors.surface,
      margin: const EdgeInsets.symmetric(vertical: 8),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: TimeEchoColors.duskPurple,
        foregroundColor: Colors.white,
        padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 14),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)),
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: TimeEchoColors.surface,
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(18),
        borderSide: BorderSide.none,
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(18),
        borderSide: const BorderSide(
          color: TimeEchoColors.duskPurple,
          width: 1.2,
        ),
      ),
    ),
  );
}
