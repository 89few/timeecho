import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:timeecho_mobile/core/app_config.dart';

void main() {
  test('production build ignores a stale saved server address', () async {
    SharedPreferences.setMockInitialValues({
      'timeecho_api_base_url': 'https://echo.example.com/api///',
    });
    AppConfig.apiBaseUrl = AppConfig.defaultApiBaseUrl;

    await AppConfig.load();

    expect(AppConfig.apiBaseUrl, AppConfig.defaultApiBaseUrl);
  });

  test('persists a normalized server address', () async {
    SharedPreferences.setMockInitialValues({});

    await AppConfig.setApiBaseUrl(' echo.example.com/ ');

    final preferences = await SharedPreferences.getInstance();
    expect(AppConfig.apiBaseUrl, 'http://echo.example.com');
    expect(
      preferences.getString('timeecho_api_base_url'),
      'http://echo.example.com',
    );
  });
}
