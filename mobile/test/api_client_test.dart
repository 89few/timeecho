import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:timeecho_mobile/core/api_client.dart';
import 'package:timeecho_mobile/core/app_config.dart';
import 'package:timeecho_mobile/core/token_store.dart';

void main() {
  late TokenStore tokenStore;

  setUp(() async {
    FlutterSecureStorage.setMockInitialValues({});
    SharedPreferences.setMockInitialValues({});
    AppConfig.apiBaseUrl = 'https://mock.timeecho.test';
    tokenStore = TokenStore();
    await tokenStore.save(
      accessToken: 'expired-access',
      refreshToken: 'valid-refresh',
      anonymousName: '晚风',
    );
  });

  test('concurrent 401 responses share one refresh and retry', () async {
    final adapter = _TokenAdapter();
    final api = ApiClient(
      dio: _dio(adapter),
      refreshDio: _dio(adapter),
      tokenStore: tokenStore,
    );

    final responses = await Future.wait([
      api.get('/protected/one'),
      api.get('/protected/two'),
    ]);

    expect(responses.map((item) => item['ok']), everyElement(isTrue));
    expect(adapter.refreshCalls, 1);
    expect(adapter.protectedCalls, 4);
    expect(await tokenStore.accessToken, 'fresh-access');
    expect(await tokenStore.refreshToken, 'fresh-refresh');
    expect(await tokenStore.anonymousName, '晚风');
  });

  test('failed refresh clears the unusable session', () async {
    final adapter = _TokenAdapter(failRefresh: true);
    final api = ApiClient(
      dio: _dio(adapter),
      refreshDio: _dio(adapter),
      tokenStore: tokenStore,
    );

    await expectLater(api.get('/protected/one'), throwsA(isA<ApiException>()));
    expect(await tokenStore.accessToken, isNull);
    expect(await tokenStore.refreshToken, isNull);
  });
}

Dio _dio(HttpClientAdapter adapter) {
  final dio = Dio();
  dio.httpClientAdapter = adapter;
  return dio;
}

class _TokenAdapter implements HttpClientAdapter {
  _TokenAdapter({this.failRefresh = false});

  final bool failRefresh;
  int refreshCalls = 0;
  int protectedCalls = 0;

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    if (options.uri.path == '/api/auth/refresh') {
      refreshCalls += 1;
      await Future<void>.delayed(const Duration(milliseconds: 30));
      if (failRefresh) {
        return _json(401, {
          'success': false,
          'error_code': 'INVALID_TOKEN',
          'message': '失效',
        });
      }
      return _json(200, {
        'success': true,
        'data': {
          'access_token': 'fresh-access',
          'refresh_token': 'fresh-refresh',
        },
      });
    }

    protectedCalls += 1;
    await Future<void>.delayed(const Duration(milliseconds: 8));
    if (options.headers['Authorization'] != 'Bearer fresh-access') {
      return _json(401, {
        'success': false,
        'error_code': 'INVALID_TOKEN',
        'message': '已过期',
      });
    }
    return _json(200, {
      'success': true,
      'data': {'ok': true, 'path': options.uri.path},
    });
  }

  ResponseBody _json(int status, Map<String, dynamic> body) =>
      ResponseBody.fromString(
        jsonEncode(body),
        status,
        headers: {
          Headers.contentTypeHeader: [Headers.jsonContentType],
        },
      );

  @override
  void close({bool force = false}) {}
}
