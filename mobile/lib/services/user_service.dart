import '../core/api_client.dart';
import '../models/user.dart';

class UserService {
  UserService({ApiClient? apiClient}) : _api = apiClient ?? ApiClient();
  final ApiClient _api;
  static UserProfile? _profileCache;
  static DateTime? _profileCacheAt;
  static int _cacheGeneration = 0;

  static void clearCache() {
    _cacheGeneration++;
    _profileCache = null;
    _profileCacheAt = null;
  }

  Future<UserProfile> me({bool forceRefresh = false}) async {
    if (!forceRefresh &&
        _profileCache != null &&
        _profileCacheAt != null &&
        DateTime.now().difference(_profileCacheAt!) <
            const Duration(minutes: 2)) {
      return _profileCache!;
    }
    final generation = _cacheGeneration;
    final value = UserProfile.fromJson(await _api.get('/api/users/me'));
    if (generation == _cacheGeneration) {
      _profileCache = value;
      _profileCacheAt = DateTime.now();
    }
    return value;
  }

  Future<UserProfile> updateProfile({
    String? username,
    String? bio,
    String? avatarUrl,
  }) async {
    final data = await _api.put(
      '/api/users/me',
      data: {
        if (username != null) 'username': username.trim(),
        if (bio != null) 'bio': bio.trim(),
        if (avatarUrl != null) 'avatar_url': avatarUrl,
      },
    );
    final value = UserProfile.fromJson(data);
    _profileCache = value;
    _profileCacheAt = DateTime.now();
    return value;
  }

  Future<UserProfile> uploadAvatar(String filePath) async {
    final data = await _api.upload('/api/users/me/avatar', filePath);
    final value = UserProfile.fromJson(data);
    _profileCache = value;
    _profileCacheAt = DateTime.now();
    return value;
  }

  Future<EmotionSummary> emotionSummary() async =>
      EmotionSummary.fromJson(await _api.get('/api/users/me/emotion-summary'));

  Future<List<Map<String, dynamic>>> events() async {
    final data = await _api.get('/api/users/me/events');
    final value = data['value'];
    if (value is! List) return const [];
    return value
        .whereType<Map>()
        .map((item) => Map<String, dynamic>.from(item))
        .toList();
  }

  Future<bool> health() async {
    final data = await _api.get('/health');
    return data['status'] == 'ok';
  }
}
