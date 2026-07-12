import 'package:flutter/material.dart';

import 'core/theme.dart';
import 'screens/chat_screen.dart';
import 'screens/emotion_summary_screen.dart';
import 'screens/home_screen.dart';
import 'screens/letter_detail_screen.dart';
import 'screens/login_screen.dart';
import 'screens/register_screen.dart';
import 'screens/forgot_password_screen.dart';
import 'screens/splash_screen.dart';

class TimeEchoApp extends StatelessWidget {
  const TimeEchoApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'TimeEcho 时光树洞',
      debugShowCheckedModeBanner: false,
      theme: buildTheme(),
      initialRoute: '/',
      routes: {
        '/': (_) => const SplashScreen(),
        '/login': (_) => const LoginScreen(),
        '/register': (_) => const RegisterScreen(),
        '/forgot-password': (_) => const ForgotPasswordScreen(),
        '/home': (_) => const HomeScreen(),
        '/emotion-summary': (_) => const EmotionSummaryScreen(),
      },
      onGenerateRoute: (settings) {
        if (settings.name == '/letter-detail') {
          final id = settings.arguments as int;
          return MaterialPageRoute(
            builder: (_) => LetterDetailScreen(letterId: id),
          );
        }
        if (settings.name == '/chat') {
          final args = settings.arguments as ChatScreenArgs;
          return MaterialPageRoute(builder: (_) => ChatScreen(args: args));
        }
        return null;
      },
    );
  }
}
