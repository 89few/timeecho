import 'chat_room.dart';

class MatchingStatus {
  const MatchingStatus({
    required this.status,
    this.purpose,
    this.topic,
    this.queuedAt,
    this.room,
  });

  final String status;
  final String? purpose;
  final String? topic;
  final DateTime? queuedAt;
  final ChatRoomInfo? room;

  factory MatchingStatus.fromJson(Map<String, dynamic> json) {
    final room = json['room'];
    return MatchingStatus(
      status: json['status']?.toString() ?? 'IDLE',
      purpose: json['purpose']?.toString(),
      topic: json['topic']?.toString(),
      queuedAt: DateTime.tryParse('${json['queued_at'] ?? ''}'),
      room: room is Map
          ? ChatRoomInfo.fromJson(Map<String, dynamic>.from(room))
          : null,
    );
  }
}
