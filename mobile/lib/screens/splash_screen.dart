import 'package:flutter/material.dart';

import '../core/theme.dart';
import '../core/token_store.dart';

class SplashScreen extends StatefulWidget {
  const SplashScreen({super.key});

  @override
  State<SplashScreen> createState() => _SplashScreenState();
}

class _SplashScreenState extends State<SplashScreen> {
  @override
  void initState() {
    super.initState();
    _decide();
  }

  Future<void> _decide() async {
    final token = await TokenStore().accessToken;
    if (!mounted) return;
    Navigator.pushReplacementNamed(context, token == null ? '/login' : '/home');
  }

  @override
  Widget build(BuildContext context) {
    return const Scaffold(
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              '✦',
              style: TextStyle(fontSize: 54, color: TimeEchoColors.duskPurple),
            ),
            SizedBox(height: 12),
            Text(
              'TimeEcho 时光树洞',
              style: TextStyle(fontWeight: FontWeight.w800, fontSize: 22),
            ),
            SizedBox(height: 8),
            Text('正在把纸飞机放进夜色里……'),
          ],
        ),
      ),
    );
  }
}
