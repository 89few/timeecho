class ChatMessageView {
  const ChatMessageView({
    required this.type,
    required this.createdAt,
    this.content,
    this.message,
    this.senderName,
    this.senderRole,
    this.kind = 'text',
    this.mediaUrl,
    this.mine = false,
  });

  final String type;
  final String? content;
  final String? message;
  final String? senderName;
  final String? senderRole;
  final bool mine;
  final DateTime createdAt;
  final String kind;
  final String? mediaUrl;

  factory ChatMessageView.localText(String content, {String? senderName}) =>
      ChatMessageView(
        type: 'message',
        content: content,
        senderName: senderName,
        senderRole: 'self',
        mine: true,
        createdAt: DateTime.now(),
        kind: 'text',
      );

  factory ChatMessageView.localMedia(String kind, String mediaUrl) =>
      ChatMessageView(
        type: 'message',
        content: kind == 'audio'
            ? '[语音]'
            : kind == 'video'
                ? '[视频]'
                : '[图片]',
        mine: true,
        kind: kind,
        mediaUrl: mediaUrl,
        createdAt: DateTime.now(),
      );

  factory ChatMessageView.fromJson(
    Map<String, dynamic> json, {
    String? myName,
  }) {
    final senderName = json['sender_name']?.toString();
    return ChatMessageView(
      type: json['type']?.toString() ?? 'message',
      content: json['content']?.toString(),
      message: json['message']?.toString(),
      senderName: senderName,
      senderRole: json['sender_role']?.toString(),
      mine: json['mine'] == true || (myName != null && senderName == myName),
      createdAt:
          DateTime.tryParse(json['created_at']?.toString() ?? '')?.toLocal() ??
              DateTime.now(),
      kind: json['kind']?.toString() ?? 'text',
      mediaUrl: json['media_url']?.toString(),
    );
  }
}
