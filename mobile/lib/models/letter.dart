class LetterSummary {
  const LetterSummary({
    required this.id,
    required this.emotion,
    required this.status,
    required this.createdAt,
    this.riskLevel,
    this.releaseAt,
    this.salvagedAt,
    this.destroyAt,
    this.contentDestroyed = false,
  });

  final int id;
  final String emotion;
  final String status;
  final String? riskLevel;
  final DateTime? releaseAt;
  final DateTime? salvagedAt;
  final DateTime? destroyAt;
  final DateTime createdAt;
  final bool contentDestroyed;

  factory LetterSummary.fromJson(Map<String, dynamic> json) => LetterSummary(
        id: int.tryParse('${json['id']}') ?? 0,
        emotion: json['emotion']?.toString() ?? '平静',
        status: json['status']?.toString() ?? 'SEALED',
        riskLevel: json['risk_level']?.toString(),
        releaseAt: _dt(json['release_at']),
        salvagedAt: _dt(json['salvaged_at']),
        destroyAt: _dt(json['destroy_at']),
        createdAt: _dt(json['created_at']) ?? DateTime.now(),
        contentDestroyed: json['content_destroyed'] == true,
      );
}

class LetterDetail extends LetterSummary {
  const LetterDetail({
    required super.id,
    required super.emotion,
    required super.status,
    required super.createdAt,
    super.riskLevel,
    super.releaseAt,
    super.salvagedAt,
    super.destroyAt,
    super.contentDestroyed,
    this.content,
    this.anonymousName,
    this.anonymousAvatarUrl,
    this.peerAnonymousName,
    this.peerAnonymousAvatarUrl,
    this.isAuthor = false,
    this.isSalvager = false,
  });

  final String? content;
  final String? anonymousName;
  final String? anonymousAvatarUrl;
  final String? peerAnonymousName;
  final String? peerAnonymousAvatarUrl;
  final bool isAuthor;
  final bool isSalvager;

  factory LetterDetail.fromJson(Map<String, dynamic> json) => LetterDetail(
        id: int.tryParse('${json['id']}') ?? 0,
        emotion: json['emotion']?.toString() ?? '平静',
        status: json['status']?.toString() ?? 'SEALED',
        riskLevel: json['risk_level']?.toString(),
        releaseAt: _dt(json['release_at']),
        salvagedAt: _dt(json['salvaged_at']),
        destroyAt: _dt(json['destroy_at']),
        createdAt: _dt(json['created_at']) ?? DateTime.now(),
        contentDestroyed: json['content_destroyed'] == true,
        content: json['content']?.toString(),
        anonymousName: json['anonymous_name']?.toString(),
        anonymousAvatarUrl: json['anonymous_avatar_url']?.toString(),
        peerAnonymousName:
            (json['peer_anonymous_name'] ?? json['author_anonymous_name'])
                ?.toString(),
        peerAnonymousAvatarUrl: (json['peer_anonymous_avatar_url'] ??
                json['author_anonymous_avatar_url'])
            ?.toString(),
        isAuthor: json['is_author'] == true,
        isSalvager: json['is_salvager'] == true,
      );
}

class SalvagedLetter {
  const SalvagedLetter({
    required this.letterId,
    required this.content,
    required this.emotion,
    this.authorAnonymousName,
    this.authorAnonymousAvatarUrl,
  });

  final int letterId;
  final String content;
  final String emotion;
  final String? authorAnonymousName;
  final String? authorAnonymousAvatarUrl;

  factory SalvagedLetter.fromJson(Map<String, dynamic> json) => SalvagedLetter(
        letterId: int.tryParse('${json['letter_id']}') ?? 0,
        content: json['content']?.toString() ?? '',
        emotion: json['emotion']?.toString() ?? '平静',
        authorAnonymousName: json['author_anonymous_name']?.toString(),
        authorAnonymousAvatarUrl:
            json['author_anonymous_avatar_url']?.toString(),
      );
}

DateTime? _dt(dynamic value) {
  if (value == null) return null;
  return DateTime.tryParse(value.toString());
}
