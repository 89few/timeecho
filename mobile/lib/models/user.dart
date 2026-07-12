class UserProfile {
  const UserProfile({
    required this.anonymousName,
    this.uid,
    this.id,
    this.username,
    this.email,
    this.avatarUrl,
    this.bio,
    this.emotion,
    this.status,
    this.friendCount = 0,
    this.postCount = 0,
  });

  final int? id;
  final String? uid;
  final String anonymousName;
  final String? username;
  final String? email;
  final String? avatarUrl;
  final String? bio;
  final String? emotion;
  final String? status;
  final int friendCount;
  final int postCount;

  String get displayName =>
      username?.trim().isNotEmpty == true ? username! : anonymousName;

  factory UserProfile.fromJson(Map<String, dynamic> json) => UserProfile(
        id: int.tryParse('${json['id'] ?? json['user_id']}'),
        uid: json['uid']?.toString(),
        anonymousName: json['anonymous_name']?.toString() ?? '时光旅人',
        username: json['username']?.toString(),
        email: json['email']?.toString(),
        avatarUrl: json['avatar_url']?.toString(),
        bio: json['bio']?.toString(),
        emotion: json['emotion']?.toString(),
        status: json['status']?.toString(),
        friendCount: int.tryParse('${json['friend_count'] ?? 0}') ?? 0,
        postCount: int.tryParse('${json['post_count'] ?? 0}') ?? 0,
      );
}

class EmotionSummary {
  const EmotionSummary({
    required this.days,
    required this.totalLetters,
    required this.emotionCounts,
    required this.summary,
  });

  final int days;
  final int totalLetters;
  final Map<String, int> emotionCounts;
  final String summary;

  factory EmotionSummary.fromJson(Map<String, dynamic> json) {
    final rawCounts = json['emotion_counts'];
    return EmotionSummary(
      days: int.tryParse('${json['days']}') ?? 7,
      totalLetters: int.tryParse('${json['total_letters']}') ?? 0,
      emotionCounts: rawCounts is Map
          ? rawCounts.map(
              (key, value) =>
                  MapEntry(key.toString(), int.tryParse('$value') ?? 0),
            )
          : const {},
      summary: json['summary']?.toString() ?? '最近还没有足够的情绪记录。',
    );
  }
}
