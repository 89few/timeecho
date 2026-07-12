class ChatRoomInfo {
  const ChatRoomInfo({
    required this.roomId,
    required this.status,
    this.letterId,
    this.roomKind = 'TEMPORARY',
    this.peerUserId,
    this.peerAnonymousName,
    this.peerAvatarUrl,
    this.expiredAt,
    this.lastMessage,
    this.lastMessageAt,
    this.unreadCount = 0,
    this.canViewProfile = false,
    this.identityRevealed = false,
    this.cardExchangeStatus = 'NONE',
    this.myAnonymousName,
    this.myAnonymousAvatarUrl,
  });

  final int roomId;
  final int? letterId;
  final String roomKind;
  final String status;
  final int? peerUserId;
  final String? peerAnonymousName;
  final String? peerAvatarUrl;
  final DateTime? expiredAt;
  final String? lastMessage;
  final DateTime? lastMessageAt;
  final int unreadCount;
  final bool canViewProfile;
  final bool identityRevealed;
  final String cardExchangeStatus;
  final String? myAnonymousName;
  final String? myAnonymousAvatarUrl;

  bool get isTemporary => roomKind != 'FRIEND';
  bool get isMatch => roomKind == 'MATCH';

  factory ChatRoomInfo.fromJson(Map<String, dynamic> json) => ChatRoomInfo(
        roomId: int.tryParse('${json['room_id']}') ?? 0,
        letterId: int.tryParse('${json['letter_id'] ?? ''}'),
        roomKind: json['room_kind']?.toString() ?? 'TEMPORARY',
        status: json['status']?.toString() ?? 'ACTIVE',
        peerUserId: int.tryParse('${json['peer_user_id'] ?? ''}'),
        peerAnonymousName:
            (json['peer_display_name'] ?? json['peer_anonymous_name'])
                ?.toString(),
        peerAvatarUrl: json['peer_avatar_url']?.toString(),
        expiredAt: json['expired_at'] == null
            ? null
            : DateTime.tryParse(json['expired_at'].toString()),
        lastMessage: json['last_message']?.toString(),
        lastMessageAt: json['last_message_at'] == null
            ? null
            : DateTime.tryParse(json['last_message_at'].toString()),
        unreadCount: int.tryParse('${json['unread_count'] ?? 0}') ?? 0,
        canViewProfile: json['can_view_profile'] == true,
        identityRevealed: json['identity_revealed'] == true,
        cardExchangeStatus: json['card_exchange_status']?.toString() ?? 'NONE',
        myAnonymousName: json['my_anonymous_name']?.toString(),
        myAnonymousAvatarUrl: json['my_anonymous_avatar_url']?.toString(),
      );
}
