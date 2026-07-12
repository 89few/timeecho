import '../core/api_client.dart';
import '../models/chat_room.dart';
import '../models/social.dart';

class SocialService {
  SocialService({ApiClient? apiClient}) : _api = apiClient ?? ApiClient();

  final ApiClient _api;
  static final Map<String, _Timed<List<SocialPost>>> _postCache = {};
  static final Map<int, _Timed<PublicUserProfile>> _profileCache = {};
  static _Timed<List<SocialNotification>>? _notificationCache;
  static _Timed<List<SocialUser>>? _friendCache;
  static _Timed<List<FriendRequestInfo>>? _requestCache;
  static int _cacheGeneration = 0;

  static void clearCache() {
    _cacheGeneration++;
    _postCache.clear();
    _profileCache.clear();
    _notificationCache = null;
    _friendCache = null;
    _requestCache = null;
  }

  bool _fresh(_Timed<Object?>? value, Duration ttl) =>
      value != null && DateTime.now().difference(value.at) < ttl;

  Future<List<SocialPost>> posts({
    int page = 1,
    int pageSize = 20,
    int? authorId,
    bool forceRefresh = false,
  }) async {
    final key = '$page:$pageSize:${authorId ?? 0}';
    final cached = _postCache[key];
    if (!forceRefresh && _fresh(cached, const Duration(minutes: 2))) {
      return cached!.value;
    }
    final generation = _cacheGeneration;
    final data = await _api.get(
      '/api/social/posts',
      queryParameters: {
        'page': page,
        'page_size': pageSize,
        if (authorId != null) 'author_id': authorId,
      },
    );
    final result = _list(data, const [
      'items',
      'posts',
    ]).map(SocialPost.fromJson).toList();
    if (generation == _cacheGeneration) _postCache[key] = _Timed(result);
    return result;
  }

  Future<SocialPost> post(int postId) async {
    final data = await _api.get('/api/social/posts/$postId');
    return SocialPost.fromJson(_object(data, const ['post']));
  }

  Future<SocialPost> createPost({
    required String text,
    List<SocialMedia> media = const [],
    String visibility = 'PUBLIC',
  }) async {
    final data = await _api.post(
      '/api/social/posts',
      data: {
        'text': text.trim(),
        'media': media.map((item) => item.toJson()).toList(),
        'visibility': visibility,
      },
    );
    _postCache.clear();
    return SocialPost.fromJson(_object(data, const ['post']));
  }

  Future<void> deletePost(int postId) async {
    await _api.delete('/api/social/posts/$postId');
    _postCache.clear();
  }

  Future<SocialMedia> uploadMedia(String path) async {
    final data = await _api.upload('/api/social/media', path);
    return SocialMedia.fromJson(_object(data, const ['media']));
  }

  Future<SocialPost> toggleLike(SocialPost post) async {
    final data = await _api.post('/api/social/posts/${post.id}/likes');
    final value = _object(data, const ['post']);
    final liked = value['liked'] == true || value['liked_by_me'] == true;
    final count =
        int.tryParse('${value['like_count'] ?? value['likes_count']}') ??
            (post.likeCount + (liked ? 1 : -1)).clamp(0, 1 << 31);
    _postCache.clear();
    return post.copyWith(likedByMe: liked, likeCount: count);
  }

  Future<List<SocialComment>> comments(int postId) async {
    final data = await _api.get('/api/social/posts/$postId/comments');
    return _list(data, const [
      'items',
      'comments',
    ]).map(SocialComment.fromJson).toList();
  }

  Future<SocialComment> addComment(int postId, String text) async {
    final data = await _api.post(
      '/api/social/posts/$postId/comments',
      data: {'text': text.trim()},
    );
    _postCache.clear();
    return SocialComment.fromJson(_object(data, const ['comment']));
  }

  Future<List<SocialUser>> friends({bool forceRefresh = false}) async {
    if (!forceRefresh && _fresh(_friendCache, const Duration(minutes: 2))) {
      return _friendCache!.value;
    }
    final generation = _cacheGeneration;
    final data = await _api.get('/api/social/friends');
    final result = _list(data, const [
      'items',
      'friends',
    ]).map(SocialUser.fromJson).toList();
    if (generation == _cacheGeneration) _friendCache = _Timed(result);
    return result;
  }

  Future<List<SocialUser>> searchUsers(String query) async {
    if (query.trim().isEmpty) return const [];
    final data = await _api.get(
      '/api/social/friends/search',
      queryParameters: {'q': query.trim()},
    );
    return _list(data, const [
      'items',
      'users',
    ]).map(SocialUser.fromJson).toList();
  }

  Future<List<FriendRequestInfo>> friendRequests({
    String box = 'incoming',
    String status = 'PENDING',
    bool forceRefresh = false,
  }) async {
    if (!forceRefresh &&
        box == 'incoming' &&
        status == 'PENDING' &&
        _fresh(_requestCache, const Duration(seconds: 45))) {
      return _requestCache!.value;
    }
    final generation = _cacheGeneration;
    final data = await _api.get(
      '/api/social/friends/requests',
      queryParameters: {'box': box, 'status': status},
    );
    final result = _list(data, const [
      'items',
      'requests',
    ]).map(FriendRequestInfo.fromJson).toList();
    if (box == 'incoming' && status == 'PENDING') {
      if (generation == _cacheGeneration) _requestCache = _Timed(result);
    }
    return result;
  }

  Future<void> sendFriendRequest(int targetUserId, {String? message}) async {
    await _api.post(
      '/api/social/friends/requests',
      data: {
        'target_user_id': targetUserId,
        if (message != null && message.trim().isNotEmpty)
          'message': message.trim(),
      },
    );
    _requestCache = null;
  }

  Future<void> handleFriendRequest(
    int requestId, {
    required bool accept,
  }) async {
    await _api.post(
      '/api/social/friends/requests/$requestId/${accept ? 'accept' : 'reject'}',
    );
    _requestCache = null;
    _friendCache = null;
  }

  Future<void> removeFriend(int userId) async {
    await _api.delete('/api/social/friends/$userId');
    _friendCache = null;
    _profileCache.remove(userId);
  }

  Future<String?> setFriendRemark(int userId, String? remark) async {
    final data = await _api.put(
      '/api/social/friends/$userId/remark',
      data: {'remark': remark?.trim()},
    );
    _friendCache = null;
    _profileCache.remove(userId);
    return data['remark']?.toString();
  }

  Future<void> blockUser(int userId) async {
    await _api.post('/api/users/$userId/block');
  }

  Future<void> reportUser(
    int userId, {
    required String reason,
    String? description,
  }) async {
    await _api.post(
      '/api/reports',
      data: {
        'target_type': 'USER',
        'target_id': userId,
        'reason': reason,
        if (description?.trim().isNotEmpty == true)
          'description': description!.trim(),
      },
    );
  }

  Future<PublicUserProfile> publicProfile(
    int userId, {
    bool forceRefresh = false,
  }) async {
    final cached = _profileCache[userId];
    if (!forceRefresh && _fresh(cached, const Duration(minutes: 2))) {
      return cached!.value;
    }
    final generation = _cacheGeneration;
    final data = await _api.get('/api/users/$userId');
    final result = PublicUserProfile.fromJson(
      _object(data, const ['profile', 'user']),
    );
    if (generation == _cacheGeneration) _profileCache[userId] = _Timed(result);
    return result;
  }

  Future<List<SocialNotification>> notifications({
    bool unreadOnly = false,
    int page = 1,
    int pageSize = 50,
    bool forceRefresh = false,
  }) async {
    if (!forceRefresh &&
        !unreadOnly &&
        page == 1 &&
        _fresh(_notificationCache, const Duration(seconds: 30))) {
      return _notificationCache!.value;
    }
    final generation = _cacheGeneration;
    final data = await _api.get(
      '/api/notifications',
      queryParameters: {
        'unread_only': unreadOnly,
        'page': page,
        'page_size': pageSize,
      },
    );
    final result = _list(data, const [
      'items',
      'notifications',
    ]).map(SocialNotification.fromJson).toList();
    if (!unreadOnly && page == 1 && generation == _cacheGeneration) {
      _notificationCache = _Timed(result);
    }
    return result;
  }

  Future<MessageOverview> messageOverview() async {
    final data = await _api.get('/api/overview/messages');
    return MessageOverview(
      rooms: _list(data, const ['rooms'])
          .map(ChatRoomInfo.fromJson)
          .toList(),
      notifications: _list(data, const ['notifications'])
          .map(SocialNotification.fromJson)
          .toList(),
      friendRequests: _list(data, const ['friend_requests'])
          .map(FriendRequestInfo.fromJson)
          .toList(),
    );
  }

  Future<int> unreadNotificationCount() async {
    final data = await _api.get('/api/notifications/unread-count');
    final value = _object(data, const ['count']);
    return int.tryParse('${value['count'] ?? data['count'] ?? 0}') ?? 0;
  }

  Future<void> markNotificationRead(int notificationId) async {
    await _api.post('/api/notifications/$notificationId/read');
    _notificationCache = null;
  }

  Future<void> markAllNotificationsRead() async {
    await _api.post('/api/notifications/read-all');
    _notificationCache = null;
  }

  List<Map<String, dynamic>> _list(
    Map<String, dynamic> data,
    List<String> keys,
  ) {
    dynamic value = data['value'];
    for (final key in keys) {
      value ??= data[key];
    }
    if (value is Map) {
      for (final key in keys) {
        if (value[key] is List) {
          value = value[key];
          break;
        }
      }
    }
    if (value is! List) return const [];
    return value
        .whereType<Map>()
        .map((item) => Map<String, dynamic>.from(item))
        .toList();
  }

  Map<String, dynamic> _object(Map<String, dynamic> data, List<String> keys) {
    final value = data['value'];
    if (value is Map) return Map<String, dynamic>.from(value);
    for (final key in keys) {
      final nested = data[key];
      if (nested is Map) return Map<String, dynamic>.from(nested);
    }
    return data;
  }
}

class _Timed<T> {
  _Timed(this.value) : at = DateTime.now();
  final T value;
  final DateTime at;
}

class MessageOverview {
  const MessageOverview({
    required this.rooms,
    required this.notifications,
    required this.friendRequests,
  });

  final List<ChatRoomInfo> rooms;
  final List<SocialNotification> notifications;
  final List<FriendRequestInfo> friendRequests;
}
