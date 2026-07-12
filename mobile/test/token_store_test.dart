import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:timeecho_mobile/core/token_store.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('access and refresh tokens never enter SharedPreferences', () async {
    FlutterSecureStorage.setMockInitialValues({});
    SharedPreferences.setMockInitialValues({});
    final store = TokenStore();
    await store.save(
      accessToken: 'secure-access',
      refreshToken: 'secure-refresh',
      anonymousName: '晚风',
    );
    final prefs = await SharedPreferences.getInstance();
    expect(prefs.getKeys(), isNot(contains('timeecho_access_token')));
    expect(prefs.getKeys(), isNot(contains('timeecho_refresh_token')));
    expect(await store.accessToken, 'secure-access');
    expect(await store.refreshToken, 'secure-refresh');
  });
}
