import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:timeecho_mobile/app.dart';
import 'package:timeecho_mobile/core/app_config.dart';
import 'package:timeecho_mobile/screens/home_screen.dart';
import 'package:timeecho_mobile/screens/login_screen.dart';
import 'package:timeecho_mobile/widgets/emotion_chip.dart';

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues({});
    FlutterSecureStorage.setMockInitialValues({});
  });

  testWidgets('App can start', (tester) async {
    await tester.pumpWidget(const TimeEchoApp());
    await tester.pumpAndSettle();
    expect(find.text('进入树洞'), findsOneWidget);
  });

  testWidgets('Email login and account recovery actions render', (
    tester,
  ) async {
    await tester.pumpWidget(const MaterialApp(home: LoginScreen()));
    expect(find.text('进入树洞'), findsOneWidget);
    expect(find.text('创建邮箱账号'), findsOneWidget);
    expect(find.text('忘记密码？'), findsOneWidget);
    expect(find.byType(TextField), findsAtLeastNWidgets(2));
  });

  testWidgets('EmotionChip can select', (tester) async {
    var selected = '平静';
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: EmotionChip(
            label: '焦虑',
            selected: false,
            onSelected: (value) => selected = value,
          ),
        ),
      ),
    );
    await tester.tap(find.text('焦虑'));
    expect(selected, '焦虑');
  });

  testWidgets('Home write action opens a Material-backed write screen', (
    tester,
  ) async {
    await tester.pumpWidget(const MaterialApp(home: HomeScreen()));
    await tester.pump();
    await tester.tap(find.text('写一封纸飞机').first);
    await tester.pumpAndSettle();
    expect(find.text('写一封纸飞机'), findsWidgets);
    expect(find.byType(TextField), findsWidgets);
    expect(tester.takeException(), isNull);
  });

  testWidgets('Five primary navigation destinations render', (tester) async {
    await tester.pumpWidget(const MaterialApp(home: HomeScreen()));
    await tester.pump();
    for (final label in ['首页', '纸飞机', '动态', '消息', '我的']) {
      expect(find.text(label), findsOneWidget);
    }
    expect(tester.takeException(), isNull);
    // Let the eagerly mounted tabs finish their initial network timeouts.
    await tester.pump(const Duration(seconds: 20));
  });

  testWidgets('Bottom navigation preserves paper-plane form state', (
    tester,
  ) async {
    await tester.pumpWidget(const MaterialApp(home: HomeScreen()));
    await tester.tap(find.text('纸飞机'));
    await tester.pump();
    final content = find.byType(TextField).first;
    expect(content, findsOneWidget);
    await tester.enterText(content, '这段未发送的内容应被保留');
    await tester.tap(find.text('首页'));
    await tester.pump();
    await tester.tap(find.text('纸飞机'));
    await tester.pump();
    expect(find.text('这段未发送的内容应被保留'), findsOneWidget);
  });

  test('API base URL is configured', () {
    expect(AppConfig.apiBaseUrl, isNotEmpty);
  });
}
