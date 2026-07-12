import 'dart:convert';
import 'dart:math';

import 'package:web_socket_channel/web_socket_channel.dart';

import '../core/api_client.dart';
import '../core/app_config.dart';
import '../models/chat_room.dart';

class ChatService {
  ChatService({ApiClient? apiClient}) : _api = apiClient ?? ApiClient();

  final ApiClient _api;
  static List<ChatRoomInfo>? _roomCache;
  static DateTime? _roomCacheAt;
  static int _cacheGeneration = 0;

  static void clearCache() {
    _cacheGeneration++;
    _roomCache = null;
    _roomCacheAt = null;
  }

  String _clientMessageId() =>
      '${DateTime.now().microsecondsSinceEpoch}-${Random.secure().nextInt(1 << 32)}';

  Future<ChatRoomInfo> roomStatus(int roomId) async =>
      ChatRoomInfo.fromJson(await _api.get('/api/chat/rooms/$roomId'));

  Future<ChatRoomInfo> createFriendRoom(int friendUserId) async {
    final data = await _api.post('/api/chat/friends/$friendUserId/room');
    return ChatRoomInfo.fromJson(data);
  }

  Future<List<ChatRoomInfo>> rooms({bool forceRefresh = false}) async {
    if (!forceRefresh &&
        _roomCache != null &&
        _roomCacheAt != null &&
        DateTime.now().difference(_roomCacheAt!) <
            const Duration(seconds: 45)) {
      return _roomCache!;
    }
    final generation = _cacheGeneration;
    final data = await _api.get('/api/chat/rooms');
    final value = data['value'];
    if (value is! List) return const [];
    final result = value
        .whereType<Map>()
        .map((item) => ChatRoomInfo.fromJson(Map<String, dynamic>.from(item)))
        .toList();
    if (generation == _cacheGeneration) {
      _roomCache = result;
      _roomCacheAt = DateTime.now();
    }
    return result;
  }

  Future<List<Map<String, dynamic>>> history(int roomId) async {
    final data = await _api.get('/api/chat/rooms/$roomId/messages');
    final value = data['value'];
    if (value is! List) return const [];
    return value
        .whereType<Map>()
        .map((item) => Map<String, dynamic>.from(item))
        .toList();
  }

  Future<void> exitRoom(int roomId) async {
    await _api.post('/api/chat/rooms/$roomId/exit');
  }

  Future<ChatRoomInfo> exchangeCard(int roomId) async => ChatRoomInfo.fromJson(
        await _api.post('/api/chat/rooms/$roomId/card-exchange'),
      );

  Future<void> blockRoom(int roomId) async {
    await _api.post('/api/chat/rooms/$roomId/block');
  }

  Future<void> reportRoom(int roomId, {String reason = '不友善或令人不适'}) async {
    await _api.post('/api/reports/room/$roomId', data: {'reason': reason});
  }

  Future<void> endMatch(int roomId, {String action = 'END'}) async {
    await _api.post(
      '/api/matching/rooms/$roomId/end',
      data: {'action': action},
    );
  }

  Future<WebSocketChannel> connect(int roomId) async {
    final response = await _api.post('/api/auth/ws-ticket');
    final ticket = response['ticket']?.toString() ?? '';
    if (ticket.isEmpty) throw StateError('无法建立安全连接');
    return WebSocketChannel.connect(
      Uri.parse(AppConfig.websocketUrl('/ws/chat/$roomId', ticket)),
    );
  }

  void sendMessage(WebSocketChannel channel, String content) {
    channel.sink.add(
      jsonEncode({
        'type': 'message',
        'client_message_id': _clientMessageId(),
        'kind': 'text',
        'content': content,
      }),
    );
  }

  void sendEmoji(WebSocketChannel channel, String emoji) {
    channel.sink.add(
      jsonEncode({
        'type': 'message',
        'client_message_id': _clientMessageId(),
        'kind': 'emoji',
        'content': emoji,
      }),
    );
  }

  Future<Map<String, dynamic>> uploadMedia(int roomId, String filePath) {
    return _api.upload('/api/chat/rooms/$roomId/media', filePath);
  }

  void sendMedia(WebSocketChannel channel, String kind, String mediaUrl) {
    channel.sink.add(
      jsonEncode({
        'type': 'message',
        'client_message_id': _clientMessageId(),
        'kind': kind,
        'media_url': mediaUrl,
      }),
    );
  }
}
