import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';

class TokenStore {
  static const _accessKey = 'timeecho_access_token';
  static const _refreshKey = 'timeecho_refresh_token';
  static const _nameKey = 'timeecho_anonymous_name';
  static const FlutterSecureStorage _secure = FlutterSecureStorage(
    aOptions: AndroidOptions(encryptedSharedPreferences: true),
  );

  Future<String?> get accessToken => _secure.read(key: _accessKey);
  Future<String?> get refreshToken => _secure.read(key: _refreshKey);
  Future<String?> get anonymousName async =>
      (await SharedPreferences.getInstance()).getString(_nameKey);

  Future<void> save({
    required String accessToken,
    required String refreshToken,
    String? anonymousName,
  }) async {
    await _secure.write(key: _accessKey, value: accessToken);
    await _secure.write(key: _refreshKey, value: refreshToken);
    final prefs = await SharedPreferences.getInstance();
    if (anonymousName != null) {
      await prefs.setString(_nameKey, anonymousName);
    }
  }

  Future<void> clear() async {
    await _secure.delete(key: _accessKey);
    await _secure.delete(key: _refreshKey);
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_nameKey);
  }
}
