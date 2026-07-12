import 'package:flutter/material.dart';

import '../core/constants.dart';
import '../models/letter.dart';
import '../services/salvage_service.dart';
import '../widgets/emotion_chip.dart';
import '../widgets/timeecho_card.dart';
import '../widgets/social_avatar.dart';
import 'chat_screen.dart';

class SalvageScreen extends StatefulWidget {
  const SalvageScreen({super.key});

  @override
  State<SalvageScreen> createState() => _SalvageScreenState();
}

class _SalvageScreenState extends State<SalvageScreen> {
  final _scrollController = ScrollController();
  final _service = SalvageService();
  String _emotion = '疲惫';
  bool _loading = false;
  SalvagedLetter? _letter;
  String? _message;

  Future<void> _salvage() async {
    setState(() {
      _loading = true;
      _message = null;
      _letter = null;
    });
    try {
      final result = await _service.salvage(emotion: _emotion);
      setState(() {
        _letter = result;
        _message = result == null ? '暂时没有可以打捞的纸飞机' : null;
      });
      if (result != null) {
        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (_scrollController.hasClients) {
            _scrollController.animateTo(
              _scrollController.position.maxScrollExtent,
              duration: const Duration(milliseconds: 350),
              curve: Curves.easeOut,
            );
          }
        });
      }
    } catch (e) {
      setState(() => _message = e.toString());
    } finally {
      setState(() => _loading = false);
    }
  }

  Future<void> _reply() async {
    final letter = _letter;
    if (letter == null) return;
    setState(() => _loading = true);
    try {
      final room = await _service.reply(letter.letterId);
      if (!mounted) return;
      Navigator.pushNamed(
        context,
        '/chat',
        arguments: ChatScreenArgs(
          roomId: room.roomId,
          peerName: letter.authorAnonymousName ?? '匿名用户',
        ),
      );
    } catch (e) {
      setState(() => _message = e.toString());
    } finally {
      setState(() => _loading = false);
    }
  }

  @override
  void dispose() {
    _scrollController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return ListView(
      controller: _scrollController,
      padding: const EdgeInsets.all(22),
      children: [
        Text(
          '打捞纸飞机',
          style: Theme.of(
            context,
          ).textTheme.headlineMedium?.copyWith(fontWeight: FontWeight.w900),
        ),
        const SizedBox(height: 14),
        TimeEchoCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Wrap(
                spacing: 8,
                children: emotions
                    .map(
                      (e) => EmotionChip(
                        label: e,
                        selected: _emotion == e,
                        onSelected: (v) => setState(() => _emotion = v),
                      ),
                    )
                    .toList(),
              ),
              const SizedBox(height: 18),
              SizedBox(
                width: double.infinity,
                child: FilledButton(
                  onPressed: _loading || _letter != null ? null : _salvage,
                  child: Text(_letter == null ? '开始打捞' : '请先关闭当前纸飞机'),
                ),
              ),
            ],
          ),
        ),
        if (_message != null)
          Padding(
            padding: const EdgeInsets.only(top: 14),
            child: TimeEchoCard(child: Text(_message!)),
          ),
        if (_letter != null)
          Padding(
            padding: const EdgeInsets.only(top: 14),
            child: TimeEchoCard(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      SocialAvatar(
                        name: _letter!.authorAnonymousName ?? '匿名用户',
                        url: _letter!.authorAnonymousAvatarUrl,
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: Text(
                          _letter!.authorAnonymousName ?? '匿名用户',
                          style: const TextStyle(
                            fontWeight: FontWeight.w900,
                            fontSize: 20,
                          ),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 10),
                  Text(
                    _letter!.content,
                    style: const TextStyle(fontSize: 17, height: 1.7),
                  ),
                  const SizedBox(height: 12),
                  Text(_letter!.emotion),
                  const SizedBox(height: 14),
                  Row(
                    children: [
                      Expanded(
                        child: OutlinedButton(
                          onPressed: () => setState(() => _letter = null),
                          child: const Text('关闭'),
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: FilledButton(
                          onPressed: _loading ? null : _reply,
                          child: const Text('回信'),
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
      ],
    );
  }
}
