import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import '../core/theme.dart';
import '../models/chat_room.dart';
import '../models/matching.dart';
import '../services/matching_service.dart';
import '../widgets/timeecho_card.dart';
import 'chat_screen.dart';

class MatchingScreen extends StatefulWidget {
  const MatchingScreen({super.key});

  @override
  State<MatchingScreen> createState() => _MatchingScreenState();
}

class _MatchingScreenState extends State<MatchingScreen> {
  final _service = MatchingService();
  String _purpose = 'CASUAL';
  String _topic = 'LIFE';
  MatchingStatus _status = const MatchingStatus(status: 'IDLE');
  WebSocketChannel? _channel;
  StreamSubscription? _subscription;
  Timer? _heartbeat;
  bool _busy = false;
  bool _openingRoom = false;
  String? _error;

  static const purposes = {'VENT': '想倾诉', 'LISTEN': '愿意倾听', 'CASUAL': '随便聊聊'};
  static const topics = {
    'LIFE': '生活',
    'STUDY': '学习',
    'WORK': '工作',
    'RELATIONSHIP': '感情',
    'INTEREST': '兴趣',
    'LATE_NIGHT': '深夜',
  };

  @override
  void initState() {
    super.initState();
    _load();
    _connectWaitingSocket();
    _heartbeat = Timer.periodic(const Duration(seconds: 15), (_) => _tick());
  }

  Future<void> _connectWaitingSocket() async {
    try {
      final channel = await _service.connectWaiting();
      _channel = channel;
      _subscription = channel.stream.listen(
        (event) async {
          final raw = event is String ? jsonDecode(event) : event;
          if (raw is Map && raw['type'] == 'matched') {
            await _load(openMatched: true);
          }
        },
        onDone: () {
          _channel = null;
        },
      );
    } catch (_) {
      // HTTP heartbeat/status remains a reliable fallback.
    }
  }

  Future<void> _tick() async {
    if (_status.status != 'WAITING') return;
    try {
      _service.sendHeartbeat(_channel!);
    } catch (_) {}
    try {
      final value = await _service.heartbeat();
      if (!mounted) return;
      setState(() => _status = value);
      if (value.room != null) await _openRoom(value.room!);
    } catch (_) {}
  }

  Future<void> _load({bool openMatched = false}) async {
    try {
      final value = await _service.status();
      if (!mounted) return;
      setState(() {
        _status = value;
        if (value.purpose != null) _purpose = value.purpose!;
        if (value.topic != null) _topic = value.topic!;
      });
      if (openMatched && value.room != null) await _openRoom(value.room!);
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    }
  }

  Future<void> _start() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      if (_channel == null) await _connectWaitingSocket();
      final value = await _service.join(_purpose, _topic);
      if (!mounted) return;
      setState(() => _status = value);
      if (value.room != null) await _openRoom(value.room!);
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _cancel() async {
    setState(() => _busy = true);
    try {
      await _service.cancel();
      if (mounted) {
        setState(() => _status = const MatchingStatus(status: 'IDLE'));
      }
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _openRoom(ChatRoomInfo room) async {
    if (_openingRoom || !mounted) return;
    _openingRoom = true;
    await Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => ChatScreen(
          args: ChatScreenArgs(
            roomId: room.roomId,
            peerName: room.peerAnonymousName,
            isTemporary: true,
            roomKind: room.roomKind,
          ),
        ),
      ),
    );
    _openingRoom = false;
    if (mounted) await _load();
  }

  @override
  void dispose() {
    _heartbeat?.cancel();
    _subscription?.cancel();
    _channel?.sink.close();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final waiting = _status.status == 'WAITING';
    final active = _status.status == 'ACTIVE' && _status.room != null;
    return Scaffold(
      appBar: AppBar(title: const Text('即时遇见')),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          TimeEchoCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  '现在想怎样聊？',
                  style: TextStyle(fontSize: 21, fontWeight: FontWeight.w900),
                ),
                const SizedBox(height: 14),
                const Text(
                  '聊天目的',
                  style: TextStyle(fontWeight: FontWeight.w800),
                ),
                const SizedBox(height: 8),
                Wrap(
                  spacing: 8,
                  children: purposes.entries
                      .map(
                        (item) => ChoiceChip(
                          label: Text(item.value),
                          selected: _purpose == item.key,
                          onSelected: waiting || active
                              ? null
                              : (_) => setState(() => _purpose = item.key),
                        ),
                      )
                      .toList(),
                ),
                const SizedBox(height: 18),
                const Text(
                  '聊天话题',
                  style: TextStyle(fontWeight: FontWeight.w800),
                ),
                const SizedBox(height: 8),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: topics.entries
                      .map(
                        (item) => ChoiceChip(
                          label: Text(item.value),
                          selected: _topic == item.key,
                          onSelected: waiting || active
                              ? null
                              : (_) => setState(() => _topic = item.key),
                        ),
                      )
                      .toList(),
                ),
              ],
            ),
          ),
          const SizedBox(height: 14),
          TimeEchoCard(
            child: Column(
              children: [
                Icon(
                  active
                      ? Icons.forum_rounded
                      : waiting
                          ? Icons.radar_rounded
                          : Icons.waving_hand_outlined,
                  size: 46,
                  color: TimeEchoColors.duskPurple,
                ),
                const SizedBox(height: 10),
                Text(
                  active
                      ? '已匹配'
                      : waiting
                          ? '正在寻找合适的回声…'
                          : '当前未匹配',
                  style: const TextStyle(
                    fontSize: 18,
                    fontWeight: FontWeight.w900,
                  ),
                ),
                const SizedBox(height: 8),
                if (waiting) const Text('请保持在线'),
                const SizedBox(height: 18),
                SizedBox(
                  width: double.infinity,
                  child: active
                      ? FilledButton(
                          onPressed: () => _openRoom(_status.room!),
                          child: const Text('进入匿名聊天室'),
                        )
                      : waiting
                          ? OutlinedButton(
                              onPressed: _busy ? null : _cancel,
                              child: const Text('取消匹配'),
                            )
                          : FilledButton(
                              onPressed: _busy ? null : _start,
                              child: const Text('开始匹配'),
                            ),
                ),
              ],
            ),
          ),
          if (_error != null)
            Padding(
              padding: const EdgeInsets.only(top: 14),
              child: Text(
                _error!,
                style: TextStyle(color: Theme.of(context).colorScheme.error),
              ),
            ),
        ],
      ),
    );
  }
}
