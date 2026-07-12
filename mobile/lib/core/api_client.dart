import 'package:dio/dio.dart';

import 'app_config.dart';
import 'token_store.dart';

class ApiClient {
  ApiClient({Dio? dio, Dio? refreshDio, TokenStore? tokenStore})
      : _dio = dio ??
            Dio(
              BaseOptions(
                connectTimeout: const Duration(seconds: 8),
                receiveTimeout: const Duration(seconds: 15),
              ),
            ),
        _refreshDio = refreshDio ??
            Dio(
              BaseOptions(
                connectTimeout: const Duration(seconds: 8),
                receiveTimeout: const Duration(seconds: 15),
              ),
            ),
        _tokenStore = tokenStore ?? TokenStore() {
    _dio.interceptors.add(
      InterceptorsWrapper(
        onRequest: (options, handler) async {
          options.baseUrl = AppConfig.apiBaseUrl;
          final token = await _tokenStore.accessToken;
          if (token != null && token.isNotEmpty) {
            options.headers['Authorization'] = 'Bearer $token';
          }
          handler.next(options);
        },
        onError: _handleUnauthorized,
      ),
    );
  }

  final Dio _dio;
  final Dio _refreshDio;
  final TokenStore _tokenStore;
  static Future<String?>? _refreshInFlight;
  static const _retriedKey = 'timeecho_token_refresh_retried';

  Future<void> _handleUnauthorized(
    DioException error,
    ErrorInterceptorHandler handler,
  ) async {
    final request = error.requestOptions;
    final failedAuthorization = request.headers['Authorization']?.toString();
    if (error.response?.statusCode != 401 ||
        request.extra[_retriedKey] == true ||
        request.path.endsWith('/api/auth/refresh') ||
        failedAuthorization == null) {
      handler.next(error);
      return;
    }

    // Another request may already have refreshed while this response was in
    // flight. Reuse that access token before starting another refresh.
    var accessToken = await _tokenStore.accessToken;
    if (accessToken == null ||
        accessToken.isEmpty ||
        failedAuthorization == 'Bearer $accessToken') {
      accessToken = await _refreshAccessTokenOnce();
    }
    if (accessToken == null || accessToken.isEmpty) {
      handler.next(error);
      return;
    }

    request.extra[_retriedKey] = true;
    request.headers['Authorization'] = 'Bearer $accessToken';
    request.baseUrl = AppConfig.apiBaseUrl;
    try {
      handler.resolve(await _dio.fetch<dynamic>(request));
    } on DioException catch (retryError) {
      handler.next(retryError);
    }
  }

  Future<String?> _refreshAccessTokenOnce() {
    final active = _refreshInFlight;
    if (active != null) return active;

    late final Future<String?> current;
    current = _performTokenRefresh().whenComplete(() {
      if (identical(_refreshInFlight, current)) _refreshInFlight = null;
    });
    _refreshInFlight = current;
    return current;
  }

  Future<String?> _performTokenRefresh() async {
    final refreshToken = await _tokenStore.refreshToken;
    if (refreshToken == null || refreshToken.isEmpty) {
      await _tokenStore.clear();
      return null;
    }

    try {
      _refreshDio.options.baseUrl = AppConfig.apiBaseUrl;
      final response = await _refreshDio.post<dynamic>(
        '/api/auth/refresh',
        data: {'refresh_token': refreshToken},
      );
      final raw = response.data;
      if (raw is! Map || raw['success'] != true || raw['data'] is! Map) {
        throw const FormatException('Invalid refresh response');
      }
      final data = Map<String, dynamic>.from(raw['data'] as Map);
      final newAccessToken = data['access_token']?.toString() ?? '';
      final newRefreshToken = data['refresh_token']?.toString() ?? '';
      if (newAccessToken.isEmpty || newRefreshToken.isEmpty) {
        throw const FormatException('Missing refreshed token');
      }
      await _tokenStore.save(
        accessToken: newAccessToken,
        refreshToken: newRefreshToken,
      );
      return newAccessToken;
    } catch (_) {
      await _tokenStore.clear();
      return null;
    }
  }

  Future<Map<String, dynamic>> get(
    String path, {
    Map<String, dynamic>? queryParameters,
  }) async {
    try {
      final resp = await _dio.get(path, queryParameters: queryParameters);
      return _unwrap(resp.data);
    } on DioException catch (error) {
      throw _friendlyError(error);
    }
  }

  Future<Map<String, dynamic>> post(String path, {Object? data}) async {
    try {
      final resp = await _dio.post(path, data: data);
      return _unwrap(resp.data);
    } on DioException catch (error) {
      throw _friendlyError(error);
    }
  }

  Future<Map<String, dynamic>> upload(String path, String filePath) async {
    try {
      final name = filePath.split(RegExp(r'[/\\]')).last;
      final form = FormData.fromMap({
        'file': await MultipartFile.fromFile(filePath, filename: name),
      });
      final resp = await _dio.post(path, data: form);
      return _unwrap(resp.data);
    } on DioException catch (error) {
      throw _friendlyError(error);
    }
  }

  Future<Map<String, dynamic>> put(String path, {Object? data}) async {
    try {
      final resp = await _dio.put(path, data: data);
      return _unwrap(resp.data);
    } on DioException catch (error) {
      throw _friendlyError(error);
    }
  }

  Future<Map<String, dynamic>> delete(String path, {Object? data}) async {
    try {
      final resp = await _dio.delete(path, data: data);
      return _unwrap(resp.data);
    } on DioException catch (error) {
      throw _friendlyError(error);
    }
  }

  Map<String, dynamic> _unwrap(dynamic raw) {
    if (raw is Map<String, dynamic>) {
      if (raw['success'] == true) {
        final data = raw['data'];
        if (data is Map<String, dynamic>) return data;
        return {'value': data, 'message': raw['message']};
      }
      throw ApiException(
        raw['message']?.toString() ?? '请求失败',
        raw['error_code']?.toString(),
      );
    }
    throw ApiException('响应格式异常', 'BAD_RESPONSE');
  }

  ApiException _friendlyError(DioException error) {
    final data = error.response?.data;
    if (data is Map && data['message'] != null) {
      return ApiException(
        data['message'].toString(),
        data['error_code']?.toString(),
      );
    }
    if (error.type == DioExceptionType.connectionTimeout ||
        error.type == DioExceptionType.connectionError) {
      return ApiException(
        '无法连接后端 ${AppConfig.apiBaseUrl}，请确认地址正确、后端正在运行且网络可访问。',
        'BACKEND_UNREACHABLE',
      );
    }
    return ApiException('网络请求失败，请稍后重试。', 'NETWORK_ERROR');
  }
}

class ApiException implements Exception {
  ApiException(this.message, [this.code]);
  final String message;
  final String? code;

  @override
  String toString() => message;
}
