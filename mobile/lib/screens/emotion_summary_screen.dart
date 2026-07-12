import 'package:flutter/material.dart';

import '../models/user.dart';
import '../services/user_service.dart';
import '../widgets/timeecho_card.dart';

class EmotionSummaryScreen extends StatelessWidget {
  const EmotionSummaryScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final service = UserService();
    return Scaffold(
      appBar: AppBar(title: const Text('情绪小结')),
      body: FutureBuilder<EmotionSummary>(
        future: service.emotionSummary(),
        builder: (context, snapshot) {
          if (snapshot.connectionState != ConnectionState.done) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snapshot.hasError) {
            return Center(child: Text(snapshot.error.toString()));
          }
          final summary = snapshot.data!;
          return ListView(
            padding: const EdgeInsets.all(22),
            children: [
              TimeEchoCard(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '最近 ${summary.days} 天',
                      style: Theme.of(context).textTheme.titleLarge?.copyWith(
                            fontWeight: FontWeight.w900,
                          ),
                    ),
                    const SizedBox(height: 8),
                    Text('共投递 ${summary.totalLetters} 封纸飞机'),
                    const SizedBox(height: 16),
                    ...summary.emotionCounts.entries.map(
                      (entry) => Padding(
                        padding: const EdgeInsets.symmetric(vertical: 6),
                        child: Row(
                          children: [
                            SizedBox(width: 58, child: Text(entry.key)),
                            Expanded(
                              child: LinearProgressIndicator(
                                value: summary.totalLetters == 0
                                    ? 0
                                    : entry.value / summary.totalLetters,
                              ),
                            ),
                            const SizedBox(width: 8),
                            Text('${entry.value}'),
                          ],
                        ),
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 14),
              TimeEchoCard(
                child: Text(
                  summary.summary,
                  style: const TextStyle(height: 1.7),
                ),
              ),
            ],
          );
        },
      ),
    );
  }
}
