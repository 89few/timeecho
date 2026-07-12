import 'dart:convert';

import 'package:web_socket_channel/web_socket_channel.dart';

import '../core/api_client.dart';
import '../core/app_config.dart';
import '../models/matching.dart';

class MatchingService {
  MatchingService({ApiClient? apiClient}) : _api = apiClient ?? ApiClient();

  final ApiClient _api;

  Future<MatchingStatus> status() async =>
      MatchingStatus.fromJson(await _api.get('/api/matching/status'));

  Future<MatchingStatus> join(String purpose, String topic) async =>
      MatchingStatus.fromJson(
        await _api.post(
          '/api/matching/join',
          data: {'purpose': purpose, 'topic': topic},
        ),
      );

  Future<MatchingStatus> heartbeat() async =>
      MatchingStatus.fromJson(await _api.post('/api/matching/heartbeat'));

  Future<void> cancel() async {
    await _api.post('/api/matching/cancel');
  }

  Future<WebSocketChannel> connectWaiting() async {
    final response = await _api.post('/api/auth/ws-ticket');
    final ticket = response['ticket']?.toString() ?? '';
    if (ticket.isEmpty) throw StateError('无法建立安全连接');
    return WebSocketChannel.connect(
      Uri.parse(AppConfig.websocketUrl('/ws/matching', ticket)),
    );
  }

  void sendHeartbeat(WebSocketChannel channel) {
    channel.sink.add(jsonEncode({'type': 'heartbeat'}));
  }
}
