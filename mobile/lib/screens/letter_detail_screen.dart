import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../models/letter.dart';
import '../services/letter_service.dart';
import '../widgets/state_badge.dart';
import '../widgets/timeecho_card.dart';
import '../widgets/social_avatar.dart';

class LetterDetailScreen extends StatelessWidget {
  const LetterDetailScreen({super.key, required this.letterId});

  final int letterId;

  @override
  Widget build(BuildContext context) {
    final service = LetterService();
    return Scaffold(
      appBar: AppBar(title: const Text('纸飞机详情')),
      body: FutureBuilder<LetterDetail>(
        future: service.detail(letterId),
        builder: (context, snapshot) {
          if (snapshot.connectionState != ConnectionState.done) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snapshot.hasError) {
            return Center(child: Text(snapshot.error.toString()));
          }
          final letter = snapshot.data!;
          return ListView(
            padding: const EdgeInsets.all(22),
            children: [
              TimeEchoCard(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                            letter.emotion,
                            style: const TextStyle(
                              fontWeight: FontWeight.w900,
                              fontSize: 22,
                            ),
                          ),
                        ),
                        StateBadge(status: letter.status),
                      ],
                    ),
                    const SizedBox(height: 16),
                    if (letter.peerAnonymousName != null) ...[
                      Row(
                        children: [
                          SocialAvatar(
                            name: letter.peerAnonymousName!,
                            url: letter.peerAnonymousAvatarUrl,
                          ),
                          const SizedBox(width: 10),
                          Text(
                            letter.peerAnonymousName!,
                            style: const TextStyle(fontWeight: FontWeight.w800),
                          ),
                        ],
                      ),
                      const SizedBox(height: 14),
                    ],
                    Text(
                      letter.contentDestroyed
                          ? '这封信已经随风散去。'
                          : (letter.content ?? '正文仍在封存或不可见。'),
                      style: const TextStyle(fontSize: 17, height: 1.7),
                    ),
                    const SizedBox(height: 18),
                    Text(
                      letter.releaseAt == null
                          ? '释放时间未定'
                          : '释放：${DateFormat('MM月dd日 HH:mm').format(letter.releaseAt!.toLocal())}',
                    ),
                  ],
                ),
              ),
            ],
          );
        },
      ),
    );
  }
}
