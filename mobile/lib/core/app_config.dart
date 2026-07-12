import 'package:dio/dio.dart';
import 'package:shared_preferences/shared_preferences.dart';

class AppConfig {
  static const allowBackendOverride = bool.fromEnvironment(
    'ALLOW_BACKEND_OVERRIDE',
    defaultValue: false,
  );
  static const String defaultApiBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://10.0.2.2:8000',
  );
  static const String apiDiscoveryUrl = String.fromEnvironment(
    'API_DISCOVERY_URL',
    defaultValue: '',
  );
  static const _apiBaseUrlKey = 'timeecho_api_base_url';
  static const _discoveredApiBaseUrlKey = 'timeecho_discovered_api_base_url';

  static String apiBaseUrl = defaultApiBaseUrl;

  static Future<void> load() async {
    if (!allowBackendOverride) {
      apiBaseUrl = defaultApiBaseUrl;
      if (apiDiscoveryUrl.isNotEmpty) {
        final preferences = await SharedPreferences.getInstance();
        try {
          final response = await Dio(
            BaseOptions(
              connectTimeout: const Duration(seconds: 4),
              receiveTimeout: const Duration(seconds: 4),
              sendTimeout: const Duration(seconds: 4),
            ),
          ).get<Object>(apiDiscoveryUrl);
          final data = response.data;
          final candidate = data is Map
              ? data['api_base_url']?.toString()
              : null;
          if (candidate != null && candidate.startsWith('https://')) {
            apiBaseUrl = normalize(candidate);
            await preferences.setString(
              _discoveredApiBaseUrlKey,
              apiBaseUrl,
            );
          }
        } catch (_) {
          final cached = preferences.getString(_discoveredApiBaseUrlKey);
          if (cached != null && cached.startsWith('https://')) {
            apiBaseUrl = normalize(cached);
          }
        }
      }
      return;
    }
    final saved = (await SharedPreferences.getInstance()).getString(
      _apiBaseUrlKey,
    );
    if (saved != null && saved.trim().isNotEmpty) {
      apiBaseUrl = normalize(saved);
    }
  }

  static Future<void> setApiBaseUrl(String value) async {
    apiBaseUrl = normalize(value);
    await (await SharedPreferences.getInstance()).setString(
      _apiBaseUrlKey,
      apiBaseUrl,
    );
  }

  static String normalize(String value) {
    var result = value.trim();
    if (!result.startsWith('http://') && !result.startsWith('https://')) {
      result = 'http://$result';
    }
    return result.replaceFirst(RegExp(r'/+$'), '');
  }

  static String websocketUrl(String path, String ticket) {
    final base = apiBaseUrl
        .replaceFirst('http://', 'ws://')
        .replaceFirst('https://', 'wss://');
    return '$base$path?ticket=$ticket';
  }
}
