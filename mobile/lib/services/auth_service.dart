import '../core/api_client.dart';
import '../core/token_store.dart';
import '../core/unread_controller.dart';
import 'chat_service.dart';
import 'social_service.dart';
import 'user_service.dart';

class AuthService {
  AuthService({ApiClient? apiClient, TokenStore? tokenStore})
      : _api = apiClient ?? ApiClient(),
        _tokenStore = tokenStore ?? TokenStore();

  final ApiClient _api;
  final TokenStore _tokenStore;
  bool lastLoginRequiresPasswordChange = false;

  Future<void> sendEmailCode(
    String email, {
    String purpose = 'register',
  }) async {
    await _api.post(
      '/api/auth/email/send-code',
      data: {'email': email.trim().toLowerCase(), 'purpose': purpose},
    );
  }

  Future<String> registerWithEmail({
    required String email,
    required String password,
    String? code,
    String? username,
    String? avatarUrl,
  }) async {
    final data = await _api.post(
      '/api/auth/email/register',
      data: {
        'email': email.trim().toLowerCase(),
        'password': password,
        if (code != null && code.trim().isNotEmpty) 'code': code.trim(),
        if (username != null && username.trim().isNotEmpty)
          'username': username.trim(),
        if (avatarUrl != null && avatarUrl.trim().isNotEmpty)
          'avatar_url': avatarUrl.trim(),
      },
    );
    return _saveSession(data);
  }

  Future<String> loginWithPassword({
    required String identifier,
    required String password,
  }) async {
    final data = await _api.post(
      '/api/auth/email/login',
      data: {
        'identifier': identifier.trim().toLowerCase(),
        'password': password,
      },
    );
    return _saveSession(data);
  }

  Future<void> requestPasswordReset(String email) async {
    await _api.post(
      '/api/auth/password/forgot',
      data: {'email': email.trim().toLowerCase()},
    );
  }

  Future<void> resetPassword({
    required String email,
    required String code,
    required String newPassword,
  }) async {
    await _api.post(
      '/api/auth/password/reset',
      data: {
        'email': email.trim().toLowerCase(),
        'code': code.trim(),
        'new_password': newPassword,
      },
    );
  }

  // Kept as a development compatibility path for existing test accounts.
  Future<void> sendCode(String phone) async {
    await _api.post('/api/auth/send-code', data: {'phone': phone});
  }

  Future<String> login({required String phone, required String code}) async {
    final data = await _api.post(
      '/api/auth/login',
      data: {'phone': phone, 'code': code},
    );
    return _saveSession(data);
  }

  Future<String> _saveSession(Map<String, dynamic> data) async {
    final accessToken = data['access_token']?.toString() ?? '';
    final refreshToken = data['refresh_token']?.toString() ?? '';
    if (accessToken.isEmpty) {
      throw ApiException('登录响应中缺少访问凭证', 'MISSING_ACCESS_TOKEN');
    }
    final displayName = data['username']?.toString() ??
        data['anonymous_name']?.toString() ??
        '时光旅人';
    lastLoginRequiresPasswordChange = data['must_change_password'] == true;
    await _tokenStore.clear();
    _clearAccountCaches();
    await _tokenStore.save(
      accessToken: accessToken,
      refreshToken: refreshToken,
      anonymousName: displayName,
    );
    UnreadController.instance.reset();
    return displayName;
  }

  Future<void> logout() async {
    try {
      await _api.post('/api/auth/logout');
    } catch (_) {
      // Local session removal must remain available if the server is offline.
    }
    await _tokenStore.clear();
    _clearAccountCaches();
    UnreadController.instance.reset();
  }

  Future<void> changePassword({
    required String currentPassword,
    required String newPassword,
  }) async {
    await _api.post('/api/auth/password/change', data: {
      'current_password': currentPassword,
      'new_password': newPassword,
    });
    await _tokenStore.clear();
    _clearAccountCaches();
  }

  void _clearAccountCaches() {
    SocialService.clearCache();
    ChatService.clearCache();
    UserService.clearCache();
  }
}
