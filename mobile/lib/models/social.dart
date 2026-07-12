class SocialUser {
  const SocialUser({
    required this.id,
    required this.displayName,
    this.uid,
    this.avatarUrl,
    this.bio,
    this.isFriend = false,
    this.relationship = 'NONE',
    this.pendingRequestId,
  });

  final int id;
  final String? uid;
  final String displayName;
  final String? avatarUrl;
  final String? bio;
  final bool isFriend;
  final String relationship;
  final int? pendingRequestId;

  factory SocialUser.fromJson(Map<String, dynamic> json) => SocialUser(
        id: int.tryParse('${json['id'] ?? json['user_id'] ?? 0}') ?? 0,
        uid: json['uid']?.toString(),
        displayName: (json['display_name'] ??
                json['username'] ??
                json['anonymous_name'] ??
                json['name'] ??
                '时光旅人')
            .toString(),
        avatarUrl: (json['avatar_url'] ?? json['avatar'])?.toString(),
        bio: json['bio']?.toString(),
        isFriend: json['is_friend'] == true || json['relationship'] == 'FRIEND',
        relationship: json['relationship']?.toString() ??
            (json['is_friend'] == true ? 'FRIEND' : 'NONE'),
        pendingRequestId: int.tryParse('${json['pending_request_id'] ?? ''}'),
      );

  SocialUser copyWith({
    bool? isFriend,
    String? relationship,
    int? pendingRequestId,
    bool clearPendingRequest = false,
  }) =>
      SocialUser(
        id: id,
        uid: uid,
        displayName: displayName,
        avatarUrl: avatarUrl,
        bio: bio,
        isFriend: isFriend ?? this.isFriend,
        relationship: relationship ?? this.relationship,
        pendingRequestId: clearPendingRequest
            ? null
            : pendingRequestId ?? this.pendingRequestId,
      );
}

class PublicUserProfile {
  const PublicUserProfile({
    required this.id,
    required this.displayName,
    this.uid,
    this.username,
    this.remark,
    this.avatarUrl,
    this.bio,
    this.emotion,
    this.friendCount = 0,
    this.postCount = 0,
    this.isMe = false,
    this.isFriend = false,
    this.relationship = 'NONE',
    this.pendingRequestId,
    this.canMessage = false,
  });

  final int id;
  final String? uid;
  final String displayName;
  final String? username;
  final String? remark;
  final String? avatarUrl;
  final String? bio;
  final String? emotion;
  final int friendCount;
  final int postCount;
  final bool isMe;
  final bool isFriend;
  final String relationship;
  final int? pendingRequestId;
  final bool canMessage;

  factory PublicUserProfile.fromJson(Map<String, dynamic> json) =>
      PublicUserProfile(
        id: int.tryParse('${json['id'] ?? json['user_id'] ?? 0}') ?? 0,
        uid: json['uid']?.toString(),
        displayName: (json['display_name'] ??
                json['username'] ??
                json['anonymous_name'] ??
                '时光旅人')
            .toString(),
        username: json['username']?.toString(),
        remark: json['remark']?.toString(),
        avatarUrl: json['avatar_url']?.toString(),
        bio: json['bio']?.toString(),
        emotion: json['emotion']?.toString(),
        friendCount: int.tryParse('${json['friend_count'] ?? 0}') ?? 0,
        postCount: int.tryParse('${json['post_count'] ?? 0}') ?? 0,
        isMe: json['is_me'] == true,
        isFriend: json['is_friend'] == true,
        relationship: json['relationship']?.toString() ?? 'NONE',
        pendingRequestId: int.tryParse('${json['pending_request_id'] ?? ''}'),
        canMessage: json['can_message'] == true,
      );

  PublicUserProfile copyWith({
    String? displayName,
    String? remark,
    bool? isFriend,
    String? relationship,
    int? pendingRequestId,
    bool? canMessage,
    int? friendCount,
    bool clearPendingRequest = false,
    bool clearRemark = false,
  }) =>
      PublicUserProfile(
        id: id,
        uid: uid,
        displayName: displayName ?? this.displayName,
        username: username,
        remark: clearRemark ? null : remark ?? this.remark,
        avatarUrl: avatarUrl,
        bio: bio,
        emotion: emotion,
        friendCount: friendCount ?? this.friendCount,
        postCount: postCount,
        isMe: isMe,
        isFriend: isFriend ?? this.isFriend,
        relationship: relationship ?? this.relationship,
        pendingRequestId: clearPendingRequest
            ? null
            : pendingRequestId ?? this.pendingRequestId,
        canMessage: canMessage ?? this.canMessage,
      );
}

class SocialMedia {
  const SocialMedia({
    required this.kind,
    required this.url,
    this.thumbnailUrl,
    this.durationMs,
    this.width,
    this.height,
  });

  final String kind;
  final String url;
  final String? thumbnailUrl;
  final int? durationMs;
  final int? width;
  final int? height;

  factory SocialMedia.fromJson(Map<String, dynamic> json) => SocialMedia(
        kind: json['kind']?.toString() ?? 'image',
        url: json['url']?.toString() ?? '',
        thumbnailUrl: json['thumbnail_url']?.toString(),
        durationMs: int.tryParse('${json['duration_ms']}'),
        width: int.tryParse('${json['width']}'),
        height: int.tryParse('${json['height']}'),
      );

  Map<String, dynamic> toJson() => {
        'kind': kind,
        'url': url,
        if (thumbnailUrl != null) 'thumbnail_url': thumbnailUrl,
        if (durationMs != null) 'duration_ms': durationMs,
        if (width != null) 'width': width,
        if (height != null) 'height': height,
      };
}

class SocialPost {
  const SocialPost({
    required this.id,
    required this.author,
    required this.text,
    required this.createdAt,
    this.media = const [],
    this.likeCount = 0,
    this.commentCount = 0,
    this.likedByMe = false,
    this.visibility = 'PUBLIC',
    this.isMine = false,
  });

  final int id;
  final SocialUser author;
  final String text;
  final DateTime createdAt;
  final List<SocialMedia> media;
  final int likeCount;
  final int commentCount;
  final bool likedByMe;
  final String visibility;
  final bool isMine;

  factory SocialPost.fromJson(Map<String, dynamic> json) {
    final authorValue = json['author'];
    final mediaValue = json['media'] ?? json['media_items'];
    return SocialPost(
      id: int.tryParse('${json['id'] ?? json['post_id'] ?? 0}') ?? 0,
      author: authorValue is Map
          ? SocialUser.fromJson(Map<String, dynamic>.from(authorValue))
          : SocialUser.fromJson(json),
      text: (json['text'] ?? json['content'] ?? '').toString(),
      createdAt: DateTime.tryParse('${json['created_at']}') ?? DateTime.now(),
      media: mediaValue is List
          ? mediaValue
              .whereType<Map>()
              .map(
                (item) => SocialMedia.fromJson(Map<String, dynamic>.from(item)),
              )
              .where((item) => item.url.isNotEmpty)
              .toList()
          : const [],
      likeCount:
          int.tryParse('${json['like_count'] ?? json['likes_count'] ?? 0}') ??
              0,
      commentCount: int.tryParse(
            '${json['comment_count'] ?? json['comments_count'] ?? 0}',
          ) ??
          0,
      likedByMe: json['liked_by_me'] == true || json['is_liked'] == true,
      visibility: json['visibility']?.toString() ?? 'PUBLIC',
      isMine: json['is_mine'] == true,
    );
  }

  SocialPost copyWith({int? likeCount, int? commentCount, bool? likedByMe}) =>
      SocialPost(
        id: id,
        author: author,
        text: text,
        createdAt: createdAt,
        media: media,
        likeCount: likeCount ?? this.likeCount,
        commentCount: commentCount ?? this.commentCount,
        likedByMe: likedByMe ?? this.likedByMe,
        visibility: visibility,
        isMine: isMine,
      );
}

class SocialComment {
  const SocialComment({
    required this.id,
    required this.author,
    required this.text,
    required this.createdAt,
  });

  final int id;
  final SocialUser author;
  final String text;
  final DateTime createdAt;

  factory SocialComment.fromJson(Map<String, dynamic> json) {
    final authorValue = json['author'];
    return SocialComment(
      id: int.tryParse('${json['id'] ?? 0}') ?? 0,
      author: authorValue is Map
          ? SocialUser.fromJson(Map<String, dynamic>.from(authorValue))
          : SocialUser.fromJson(json),
      text: (json['text'] ?? json['content'] ?? '').toString(),
      createdAt: DateTime.tryParse('${json['created_at']}') ?? DateTime.now(),
    );
  }
}

class FriendRequestInfo {
  const FriendRequestInfo({
    required this.id,
    required this.user,
    required this.status,
    required this.createdAt,
    this.message,
  });

  final int id;
  final SocialUser user;
  final String status;
  final DateTime createdAt;
  final String? message;

  factory FriendRequestInfo.fromJson(Map<String, dynamic> json) {
    final userValue = json['user'] ?? json['from_user'] ?? json['requester'];
    return FriendRequestInfo(
      id: int.tryParse('${json['id'] ?? json['request_id'] ?? 0}') ?? 0,
      user: userValue is Map
          ? SocialUser.fromJson(Map<String, dynamic>.from(userValue))
          : SocialUser.fromJson(json),
      status: json['status']?.toString() ?? 'PENDING',
      createdAt: DateTime.tryParse('${json['created_at']}') ?? DateTime.now(),
      message: json['message']?.toString(),
    );
  }
}

class SocialNotification {
  const SocialNotification({
    required this.id,
    required this.type,
    required this.title,
    required this.message,
    required this.createdAt,
    required this.isRead,
    this.actor,
    this.data = const {},
  });

  final int id;
  final String type;
  final String title;
  final String message;
  final DateTime createdAt;
  final bool isRead;
  final SocialUser? actor;
  final Map<String, dynamic> data;

  factory SocialNotification.fromJson(Map<String, dynamic> json) {
    final actorValue = json['actor'];
    final dataValue = json['data'];
    return SocialNotification(
      id: int.tryParse('${json['id'] ?? 0}') ?? 0,
      type: json['type']?.toString() ?? 'INFO',
      title: json['title']?.toString() ?? '通知',
      message: json['message']?.toString() ?? '',
      createdAt: DateTime.tryParse('${json['created_at']}') ?? DateTime.now(),
      isRead: json['is_read'] == true,
      actor: actorValue is Map
          ? SocialUser.fromJson(Map<String, dynamic>.from(actorValue))
          : null,
      data: dataValue is Map ? Map<String, dynamic>.from(dataValue) : const {},
    );
  }

  SocialNotification copyWith({bool? isRead}) => SocialNotification(
        id: id,
        type: type,
        title: title,
        message: message,
        createdAt: createdAt,
        isRead: isRead ?? this.isRead,
        actor: actor,
        data: data,
      );
}
