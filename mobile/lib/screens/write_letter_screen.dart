import 'package:flutter/material.dart';

import '../core/constants.dart';
import '../models/letter.dart';
import '../services/letter_service.dart';
import '../widgets/emotion_chip.dart';
import '../widgets/timeecho_card.dart';

class WriteLetterScreen extends StatefulWidget {
  const WriteLetterScreen({super.key});

  @override
  State<WriteLetterScreen> createState() => _WriteLetterScreenState();
}

class _WriteLetterScreenState extends State<WriteLetterScreen> {
  final _content = TextEditingController();
  final _service = LetterService();
  String _emotion = '疲惫';
  int? _sealDays = 1;
  int? _sealSeconds;
  bool _loading = false;
  LetterSummary? _created;
  String? _message;

  Future<void> _submit() async {
    setState(() {
      _loading = true;
      _message = null;
    });
    try {
      final letter = await _service.create(
        content: _content.text.trim(),
        emotion: _emotion,
        sealDays: _sealSeconds == null ? _sealDays : null,
        sealSeconds: _sealSeconds,
      );
      setState(() {
        _created = letter;
        _message = '已封存，将在 ${letter.releaseAt ?? '未来某刻'} 释放。';
        _content.clear();
      });
    } catch (e) {
      setState(() => _message = e.toString());
    } finally {
      setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(22),
      children: [
        Text(
          '写一封纸飞机',
          style: Theme.of(
            context,
          ).textTheme.headlineMedium?.copyWith(fontWeight: FontWeight.w900),
        ),
        const SizedBox(height: 14),
        TimeEchoCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              TextField(
                controller: _content,
                minLines: 7,
                maxLines: 12,
                decoration: const InputDecoration(
                  hintText: '今天很累，但还是想把这些话留给未来的某个人……',
                ),
              ),
              const SizedBox(height: 14),
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
              const SizedBox(height: 14),
              DropdownButtonFormField<String>(
                initialValue: _sealSeconds == 3 ? '3s' : '${_sealDays}d',
                decoration: const InputDecoration(labelText: '封存时间'),
                items: const [
                  DropdownMenuItem(value: '1d', child: Text('1 天')),
                  DropdownMenuItem(value: '7d', child: Text('7 天')),
                  DropdownMenuItem(value: '30d', child: Text('30 天')),
                  DropdownMenuItem(value: '3s', child: Text('3 秒（测试）')),
                ],
                onChanged: (value) => setState(() {
                  if (value == '3s') {
                    _sealSeconds = 3;
                    _sealDays = null;
                  } else {
                    _sealSeconds = null;
                    _sealDays = int.parse(value!.replaceAll('d', ''));
                  }
                }),
              ),
              const SizedBox(height: 18),
              SizedBox(
                width: double.infinity,
                child: FilledButton(
                  onPressed: _loading ? null : _submit,
                  child: const Text('投递到未来'),
                ),
              ),
            ],
          ),
        ),
        if (_message != null)
          Padding(
            padding: const EdgeInsets.only(top: 16),
            child: TimeEchoCard(child: Text(_message!)),
          ),
        if (_created != null)
          Padding(
            padding: const EdgeInsets.only(top: 10),
            child: Text('纸飞机 #${_created!.id} 状态：${_created!.status}'),
          ),
      ],
    );
  }
}
