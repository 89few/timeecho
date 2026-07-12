import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../models/letter.dart';
import '../services/letter_service.dart';
import '../widgets/empty_state.dart';
import '../widgets/state_badge.dart';
import '../widgets/timeecho_card.dart';

class MyLettersScreen extends StatefulWidget {
  const MyLettersScreen({super.key});

  @override
  State<MyLettersScreen> createState() => _MyLettersScreenState();
}

class _MyLettersScreenState extends State<MyLettersScreen> {
  final _service = LetterService();
  List<LetterSummary>? _items;
  String? _error;
  bool _loading = true;

  String _date(DateTime? value) =>
      value == null ? '待定' : DateFormat('MM月dd日 HH:mm').format(value.toLocal());

  @override
  void initState() {
    super.initState();
    _reload();
  }

  Future<void> _reload() async {
    if (_items == null) setState(() => _loading = true);
    try {
      final value = await _service.mine();
      if (mounted) setState(() => _items = value);
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return RefreshIndicator(
      onRefresh: _reload,
      child: ListView(
        padding: const EdgeInsets.all(22),
        children: [
          Text(
            '我的纸飞机',
            style: Theme.of(
              context,
            ).textTheme.headlineMedium?.copyWith(fontWeight: FontWeight.w900),
          ),
          const SizedBox(height: 14),
          if (_loading && _items == null)
            const Center(child: CircularProgressIndicator())
          else if (_error != null && _items == null)
            TimeEchoCard(child: Text(_error!))
          else if (_items?.isEmpty ?? true)
            const EmptyState(title: '还没有投递记录', message: '')
          else
            Column(
              children: _items!
                  .map(
                    (letter) => TimeEchoCard(
                      onTap: () => Navigator.pushNamed(
                        context,
                        '/letter-detail',
                        arguments: letter.id,
                      ),
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  letter.emotion,
                                  style: const TextStyle(
                                    fontWeight: FontWeight.w800,
                                    fontSize: 17,
                                  ),
                                ),
                                const SizedBox(height: 6),
                                Text(
                                  letter.contentDestroyed
                                      ? '这封信已经随风散去'
                                      : '释放：${_date(letter.releaseAt)}',
                                ),
                              ],
                            ),
                          ),
                          StateBadge(status: letter.status),
                        ],
                      ),
                    ),
                  )
                  .toList(),
            ),
        ],
      ),
    );
  }
}
