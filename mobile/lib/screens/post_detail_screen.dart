import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';

import '../core/app_config.dart';
import '../core/theme.dart';
import '../models/social.dart';
import '../services/social_service.dart';
import '../widgets/social_avatar.dart';
import '../widgets/timeecho_card.dart';
import 'public_profile_screen.dart';
import 'social_media_viewer_screen.dart';

class PostDetailScreen extends StatefulWidget {
  const PostDetailScreen({super.key, required this.postId});

  final int postId;

  @override
  State<PostDetailScreen> createState() => _PostDetailScreenState();
}

class _PostDetailScreenState extends State<PostDetailScreen> {
  final _service = SocialService();
  final _comment = TextEditingController();
  SocialPost? _post;
  List<SocialComment> _comments = const [];
  bool _loading = true;
  bool _sending = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _comment.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final values = await Future.wait([
        _service.post(widget.postId),
        _service.comments(widget.postId),
      ]);
      if (!mounted) return;
      setState(() {
        _post = values[0] as SocialPost;
        _comments = values[1] as List<SocialComment>;
        _error = null;
      });
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _toggleLike() async {
    final post = _post;
    if (post == null) return;
    final updated = await _service.toggleLike(post);
    if (mounted) setState(() => _post = updated);
  }

  Future<void> _sendComment() async {
    final text = _comment.text.trim();
    if (text.isEmpty || _sending) return;
    setState(() => _sending = true);
    try {
      final comment = await _service.addComment(widget.postId, text);
      if (!mounted) return;
      setState(() {
        _comments = [..._comments, comment];
        if (_post != null) {
          _post = _post!.copyWith(commentCount: _post!.commentCount + 1);
        }
      });
      _comment.clear();
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  String _url(String value) => value.startsWith('http')
      ? value
      : '${AppConfig.apiBaseUrl}${value.startsWith('/') ? '' : '/'}$value';

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('动态详情')),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? Center(child: Text(_error!))
              : Column(
                  children: [
                    Expanded(
                      child: RefreshIndicator(
                        onRefresh: _load,
                        child: ListView(
                          padding: const EdgeInsets.all(16),
                          children: [
                            if (_post != null) _postCard(_post!),
                            const SizedBox(height: 16),
                            const Text(
                              '评论',
                              style: TextStyle(
                                fontSize: 18,
                                fontWeight: FontWeight.w900,
                              ),
                            ),
                            const SizedBox(height: 8),
                            if (_comments.isEmpty)
                              const Padding(
                                padding: EdgeInsets.symmetric(vertical: 24),
                                child: Text(
                                  '还没有评论',
                                  textAlign: TextAlign.center,
                                  style: TextStyle(color: TimeEchoColors.muted),
                                ),
                              ),
                            ..._comments.map(
                              (comment) => ListTile(
                                onTap: () => Navigator.push(
                                  context,
                                  MaterialPageRoute(
                                    builder: (_) => PublicProfileScreen(
                                      userId: comment.author.id,
                                    ),
                                  ),
                                ),
                                leading: SocialAvatar(
                                  name: comment.author.displayName,
                                  url: comment.author.avatarUrl,
                                ),
                                title: Text(
                                  comment.author.displayName,
                                  style: const TextStyle(
                                    fontWeight: FontWeight.w800,
                                  ),
                                ),
                                subtitle: Text(comment.text),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                    SafeArea(
                      top: false,
                      child: Padding(
                        padding: const EdgeInsets.fromLTRB(12, 8, 12, 10),
                        child: Row(
                          children: [
                            Expanded(
                              child: TextField(
                                controller: _comment,
                                decoration:
                                    const InputDecoration(hintText: '写评论'),
                                onSubmitted: (_) => _sendComment(),
                              ),
                            ),
                            const SizedBox(width: 8),
                            IconButton.filled(
                              onPressed: _sending ? null : _sendComment,
                              icon: const Icon(Icons.send_rounded),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ],
                ),
    );
  }

  Widget _postCard(SocialPost post) => TimeEchoCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            InkWell(
              onTap: () => Navigator.push(
                context,
                MaterialPageRoute(
                  builder: (_) => PublicProfileScreen(userId: post.author.id),
                ),
              ),
              child: Row(
                children: [
                  SocialAvatar(
                    name: post.author.displayName,
                    url: post.author.avatarUrl,
                  ),
                  const SizedBox(width: 10),
                  Text(
                    post.author.displayName,
                    style: const TextStyle(fontWeight: FontWeight.w900),
                  ),
                ],
              ),
            ),
            if (post.text.isNotEmpty) ...[
              const SizedBox(height: 14),
              Text(post.text,
                  style: const TextStyle(fontSize: 16, height: 1.5)),
            ],
            if (post.media.isNotEmpty) ...[
              const SizedBox(height: 12),
              SizedBox(
                height: 190,
                child: ListView.separated(
                  scrollDirection: Axis.horizontal,
                  itemCount: post.media.length,
                  separatorBuilder: (_, __) => const SizedBox(width: 8),
                  itemBuilder: (_, index) {
                    final media = post.media[index];
                    return GestureDetector(
                      onTap: () => Navigator.push(
                        context,
                        MaterialPageRoute(
                          builder: (_) => SocialMediaViewerScreen(media: media),
                        ),
                      ),
                      child: ClipRRect(
                        borderRadius: BorderRadius.circular(14),
                        child: SizedBox(
                          width: 190,
                          child: media.kind == 'image'
                              ? CachedNetworkImage(
                                  imageUrl: _url(media.url),
                                  fit: BoxFit.cover,
                                )
                              : Container(
                                  color: TimeEchoColors.mistBlue,
                                  child: Icon(
                                    media.kind == 'audio'
                                        ? Icons.graphic_eq_rounded
                                        : Icons.play_circle_outline_rounded,
                                  ),
                                ),
                        ),
                      ),
                    );
                  },
                ),
              ),
            ],
            const SizedBox(height: 10),
            Row(
              children: [
                TextButton.icon(
                  onPressed: _toggleLike,
                  icon: Icon(
                    post.likedByMe
                        ? Icons.favorite_rounded
                        : Icons.favorite_border_rounded,
                  ),
                  label: Text('${post.likeCount}'),
                ),
                const SizedBox(width: 8),
                const Icon(Icons.chat_bubble_outline_rounded, size: 19),
                const SizedBox(width: 5),
                Text('${post.commentCount}'),
              ],
            ),
          ],
        ),
      );
}
