import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../core/app_config.dart';
import '../core/theme.dart';
import '../models/social.dart';
import '../services/social_service.dart';
import '../widgets/social_avatar.dart';
import '../widgets/timeecho_card.dart';
import 'create_post_screen.dart';
import 'public_profile_screen.dart';
import 'social_media_viewer_screen.dart';

class FeedScreen extends StatefulWidget {
  const FeedScreen({super.key});

  @override
  State<FeedScreen> createState() => _FeedScreenState();
}

class _FeedScreenState extends State<FeedScreen> {
  final _service = SocialService();
  List<SocialPost> _posts = const [];
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load({bool forceRefresh = false}) async {
    if (mounted && _posts.isEmpty) {
      setState(() {
        _loading = true;
        _error = null;
      });
    }
    try {
      final posts = await _service.posts(forceRefresh: forceRefresh);
      if (mounted) setState(() => _posts = posts);
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _createPost() async {
    final post = await Navigator.push<SocialPost>(
      context,
      MaterialPageRoute(builder: (_) => const CreatePostScreen()),
    );
    if (post != null && mounted) setState(() => _posts = [post, ..._posts]);
  }

  Future<void> _toggleLike(int index) async {
    final original = _posts[index];
    final optimistic = original.copyWith(
      likedByMe: !original.likedByMe,
      likeCount: (original.likeCount + (original.likedByMe ? -1 : 1)).clamp(
        0,
        1 << 31,
      ),
    );
    setState(() {
      final updated = [..._posts];
      updated[index] = optimistic;
      _posts = updated;
    });
    try {
      final value = await _service.toggleLike(original);
      if (!mounted) return;
      setState(() {
        final updated = [..._posts];
        final currentIndex = updated.indexWhere(
          (item) => item.id == original.id,
        );
        if (currentIndex >= 0) updated[currentIndex] = value;
        _posts = updated;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        final updated = [..._posts];
        final currentIndex = updated.indexWhere(
          (item) => item.id == original.id,
        );
        if (currentIndex >= 0) updated[currentIndex] = original;
        _posts = updated;
      });
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(error.toString())));
    }
  }

  Future<void> _openComments(int index) async {
    final post = _posts[index];
    final added = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      backgroundColor: TimeEchoColors.surface,
      builder: (_) => _CommentsSheet(postId: post.id, service: _service),
    );
    if (added == true && mounted) {
      setState(() {
        final updated = [..._posts];
        final currentIndex = updated.indexWhere((item) => item.id == post.id);
        if (currentIndex >= 0) {
          updated[currentIndex] = post.copyWith(
            commentCount: post.commentCount + 1,
          );
        }
        _posts = updated;
      });
    }
  }

  Future<void> _deletePost(int index) async {
    final post = _posts[index];
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('删除这条动态？'),
        content: const Text('删除后无法恢复。'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('取消'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('删除'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    try {
      await _service.deletePost(post.id);
      if (mounted) {
        setState(
          () => _posts = _posts.where((item) => item.id != post.id).toList(),
        );
      }
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(error.toString())));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return RefreshIndicator(
      onRefresh: () => _load(forceRefresh: true),
      child: CustomScrollView(
        physics: const AlwaysScrollableScrollPhysics(),
        slivers: [
          SliverPadding(
            padding: const EdgeInsets.fromLTRB(22, 20, 22, 12),
            sliver: SliverToBoxAdapter(
              child: Row(
                children: [
                  Expanded(
                    child: Text(
                      '动态',
                      style: Theme.of(context)
                          .textTheme
                          .headlineMedium
                          ?.copyWith(fontWeight: FontWeight.w900),
                    ),
                  ),
                  IconButton.filled(
                    tooltip: '发布动态',
                    onPressed: _createPost,
                    icon: const Icon(Icons.add_rounded),
                  ),
                ],
              ),
            ),
          ),
          if (_loading && _posts.isEmpty)
            const SliverFillRemaining(
              hasScrollBody: false,
              child: Center(child: CircularProgressIndicator()),
            )
          else if (_error != null)
            SliverFillRemaining(
              hasScrollBody: false,
              child: _LoadState(
                icon: Icons.cloud_off_rounded,
                title: '动态暂时没有加载出来',
                message: _error!,
                actionLabel: '重新加载',
                onAction: _load,
              ),
            )
          else if (_posts.isEmpty)
            SliverFillRemaining(
              hasScrollBody: false,
              child: _LoadState(
                icon: Icons.bubble_chart_outlined,
                title: '这里还很安静',
                message: '发布第一条动态，或者去“我的”添加朋友。',
                actionLabel: '发布动态',
                onAction: _createPost,
              ),
            )
          else
            SliverPadding(
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 100),
              sliver: SliverList.builder(
                itemCount: _posts.length,
                itemBuilder: (context, index) => _PostCard(
                  post: _posts[index],
                  onLike: () => _toggleLike(index),
                  onComment: () => _openComments(index),
                  onDelete:
                      _posts[index].isMine ? () => _deletePost(index) : null,
                  onAuthor: () => Navigator.push(
                    context,
                    MaterialPageRoute(
                      builder: (_) =>
                          PublicProfileScreen(userId: _posts[index].author.id),
                    ),
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class _PostCard extends StatelessWidget {
  const _PostCard({
    required this.post,
    required this.onLike,
    required this.onComment,
    required this.onAuthor,
    this.onDelete,
  });

  final SocialPost post;
  final VoidCallback onLike;
  final VoidCallback onComment;
  final VoidCallback onAuthor;
  final VoidCallback? onDelete;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: TimeEchoCard(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: InkWell(
                    onTap: onAuthor,
                    borderRadius: BorderRadius.circular(14),
                    child: Padding(
                      padding: const EdgeInsets.symmetric(vertical: 2),
                      child: Row(
                        children: [
                          SocialAvatar(
                            name: post.author.displayName,
                            url: post.author.avatarUrl,
                            radius: 22,
                          ),
                          const SizedBox(width: 11),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  post.author.displayName,
                                  style: const TextStyle(
                                    fontWeight: FontWeight.w800,
                                  ),
                                ),
                                const SizedBox(height: 2),
                                Text(
                                  _relativeTime(post.createdAt),
                                  style: const TextStyle(
                                    fontSize: 12,
                                    color: TimeEchoColors.muted,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
                if (onDelete != null)
                  PopupMenuButton<String>(
                    tooltip: '动态操作',
                    onSelected: (value) {
                      if (value == 'delete') onDelete!();
                    },
                    itemBuilder: (_) => const [
                      PopupMenuItem(
                        value: 'delete',
                        child: Row(
                          children: [
                            Icon(Icons.delete_outline_rounded),
                            SizedBox(width: 10),
                            Text('删除动态'),
                          ],
                        ),
                      ),
                    ],
                  ),
              ],
            ),
            if (post.text.isNotEmpty) ...[
              const SizedBox(height: 12),
              Text(
                post.text,
                style: const TextStyle(fontSize: 16, height: 1.55),
              ),
            ],
            if (post.media.isNotEmpty) ...[
              const SizedBox(height: 12),
              _MediaGrid(media: post.media),
            ],
            const SizedBox(height: 10),
            Row(
              children: [
                _PostAction(
                  icon: post.likedByMe
                      ? Icons.favorite_rounded
                      : Icons.favorite_border_rounded,
                  color: post.likedByMe ? const Color(0xFFCC6677) : null,
                  label: post.likeCount == 0 ? '喜欢' : '${post.likeCount}',
                  onTap: onLike,
                ),
                const SizedBox(width: 8),
                _PostAction(
                  icon: Icons.chat_bubble_outline_rounded,
                  label: post.commentCount == 0 ? '评论' : '${post.commentCount}',
                  onTap: onComment,
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  static String _relativeTime(DateTime raw) {
    final time = raw.toLocal();
    final difference = DateTime.now().difference(time);
    if (difference.isNegative || difference.inMinutes < 1) return '刚刚';
    if (difference.inHours < 1) return '${difference.inMinutes} 分钟前';
    if (difference.inDays < 1) return '${difference.inHours} 小时前';
    if (difference.inDays < 7) return '${difference.inDays} 天前';
    return DateFormat('MM月dd日').format(time);
  }
}

class _MediaGrid extends StatelessWidget {
  const _MediaGrid({required this.media});
  final List<SocialMedia> media;

  String _url(String value) {
    if (value.startsWith('http://') || value.startsWith('https://')) {
      return value;
    }
    return '${AppConfig.apiBaseUrl}${value.startsWith('/') ? '' : '/'}$value';
  }

  @override
  Widget build(BuildContext context) {
    final visual = media
        .where(
          (item) => !const ['audio', 'voice'].contains(item.kind.toLowerCase()),
        )
        .toList();
    final audio = media
        .where(
          (item) => const ['audio', 'voice'].contains(item.kind.toLowerCase()),
        )
        .toList();
    return Column(
      children: [
        if (visual.isNotEmpty)
          LayoutBuilder(
            builder: (context, constraints) {
              final count = visual.length == 1 ? 1 : 2;
              final height = visual.length == 1
                  ? 240.0
                  : (visual.length <= 2 ? 180.0 : 300.0);
              return SizedBox(
                height: height,
                child: GridView.builder(
                  physics: const NeverScrollableScrollPhysics(),
                  gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                    crossAxisCount: count,
                    crossAxisSpacing: 4,
                    mainAxisSpacing: 4,
                  ),
                  itemCount: visual.length.clamp(0, 4),
                  itemBuilder: (context, index) {
                    final item = visual[index];
                    final previewUrl = item.thumbnailUrl ?? item.url;
                    return GestureDetector(
                      onTap: () => Navigator.push(
                        context,
                        MaterialPageRoute(
                          builder: (_) => SocialMediaViewerScreen(media: item),
                        ),
                      ),
                      child: ClipRRect(
                        borderRadius: BorderRadius.circular(12),
                        child: Stack(
                          fit: StackFit.expand,
                          children: [
                            if (item.kind == 'image' ||
                                item.thumbnailUrl != null)
                              CachedNetworkImage(
                                imageUrl: _url(previewUrl),
                                fit: BoxFit.cover,
                                memCacheWidth: 900,
                                placeholder: (_, __) => Container(
                                  color: TimeEchoColors.mistBlue,
                                  child: const Center(
                                    child: CircularProgressIndicator(
                                      strokeWidth: 2,
                                    ),
                                  ),
                                ),
                                errorWidget: (_, __, ___) => Container(
                                  color: TimeEchoColors.mistBlue,
                                  child: const Icon(
                                    Icons.broken_image_outlined,
                                  ),
                                ),
                              )
                            else
                              Container(
                                color: const Color(0xFF252734),
                                child: const Icon(
                                  Icons.movie_outlined,
                                  color: Colors.white70,
                                  size: 38,
                                ),
                              ),
                            if (item.kind == 'video')
                              const Center(
                                child: Icon(
                                  Icons.play_circle_fill_rounded,
                                  color: Colors.white,
                                  size: 48,
                                ),
                              ),
                            if (index == 3 && visual.length > 4)
                              Container(
                                color: Colors.black54,
                                alignment: Alignment.center,
                                child: Text(
                                  '+${visual.length - 3}',
                                  style: const TextStyle(
                                    color: Colors.white,
                                    fontSize: 24,
                                    fontWeight: FontWeight.w800,
                                  ),
                                ),
                              ),
                          ],
                        ),
                      ),
                    );
                  },
                ),
              );
            },
          ),
        ...audio.map(
          (item) => Padding(
            padding: EdgeInsets.only(top: visual.isNotEmpty ? 8 : 0, bottom: 4),
            child: InkWell(
              borderRadius: BorderRadius.circular(16),
              onTap: () => Navigator.push(
                context,
                MaterialPageRoute(
                  builder: (_) => SocialMediaViewerScreen(media: item),
                ),
              ),
              child: Ink(
                padding: const EdgeInsets.symmetric(
                  horizontal: 14,
                  vertical: 12,
                ),
                decoration: BoxDecoration(
                  color: const Color(0xFFEDE7F2),
                  borderRadius: BorderRadius.circular(16),
                ),
                child: Row(
                  children: [
                    const CircleAvatar(
                      backgroundColor: TimeEchoColors.duskPurple,
                      foregroundColor: Colors.white,
                      child: Icon(Icons.play_arrow_rounded),
                    ),
                    const SizedBox(width: 11),
                    const Expanded(
                      child: Text(
                        '语音动态',
                        style: TextStyle(fontWeight: FontWeight.w700),
                      ),
                    ),
                    Text(
                      item.durationMs == null
                          ? '点击播放'
                          : '${(item.durationMs! / 1000).round()}″',
                      style: const TextStyle(color: TimeEchoColors.muted),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ],
    );
  }
}

class _PostAction extends StatelessWidget {
  const _PostAction({
    required this.icon,
    required this.label,
    required this.onTap,
    this.color,
  });
  final IconData icon;
  final String label;
  final VoidCallback onTap;
  final Color? color;

  @override
  Widget build(BuildContext context) => TextButton.icon(
        onPressed: onTap,
        icon: Icon(icon, size: 20, color: color ?? TimeEchoColors.muted),
        label:
            Text(label, style: TextStyle(color: color ?? TimeEchoColors.muted)),
      );
}

class _CommentsSheet extends StatefulWidget {
  const _CommentsSheet({required this.postId, required this.service});
  final int postId;
  final SocialService service;

  @override
  State<_CommentsSheet> createState() => _CommentsSheetState();
}

class _CommentsSheetState extends State<_CommentsSheet> {
  final _input = TextEditingController();
  List<SocialComment> _comments = const [];
  bool _loading = true;
  bool _sending = false;
  bool _added = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final comments = await widget.service.comments(widget.postId);
      if (mounted) setState(() => _comments = comments);
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _send() async {
    final value = _input.text.trim();
    if (value.isEmpty || _sending) return;
    setState(() => _sending = true);
    try {
      final comment = await widget.service.addComment(widget.postId, value);
      if (!mounted) return;
      _input.clear();
      setState(() {
        _comments = [..._comments, comment];
        _added = true;
      });
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  @override
  void dispose() {
    _input.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) Navigator.pop(context, _added);
      },
      child: DraggableScrollableSheet(
        expand: false,
        initialChildSize: .76,
        minChildSize: .5,
        maxChildSize: .96,
        builder: (context, controller) => Column(
          children: [
            const SizedBox(height: 8),
            Container(
              width: 42,
              height: 4,
              decoration: BoxDecoration(
                color: Colors.black12,
                borderRadius: BorderRadius.circular(2),
              ),
            ),
            const Padding(
              padding: EdgeInsets.all(16),
              child: Text(
                '评论',
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.w900),
              ),
            ),
            const Divider(height: 1),
            Expanded(
              child: _loading
                  ? const Center(child: CircularProgressIndicator())
                  : _comments.isEmpty
                      ? Center(
                          child: Text(
                            _error ?? '还没有评论，来留下第一句话吧',
                            style: const TextStyle(color: TimeEchoColors.muted),
                          ),
                        )
                      : ListView.separated(
                          controller: controller,
                          padding: const EdgeInsets.all(18),
                          itemCount: _comments.length,
                          separatorBuilder: (_, __) =>
                              const SizedBox(height: 18),
                          itemBuilder: (context, index) {
                            final comment = _comments[index];
                            return InkWell(
                              borderRadius: BorderRadius.circular(12),
                              onTap: () => Navigator.push(
                                context,
                                MaterialPageRoute(
                                  builder: (_) => PublicProfileScreen(
                                    userId: comment.author.id,
                                  ),
                                ),
                              ),
                              child: Padding(
                                padding:
                                    const EdgeInsets.symmetric(vertical: 2),
                                child: Row(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    SocialAvatar(
                                      name: comment.author.displayName,
                                      url: comment.author.avatarUrl,
                                      radius: 18,
                                    ),
                                    const SizedBox(width: 10),
                                    Expanded(
                                      child: Column(
                                        crossAxisAlignment:
                                            CrossAxisAlignment.start,
                                        children: [
                                          Text(
                                            comment.author.displayName,
                                            style: const TextStyle(
                                              fontWeight: FontWeight.w700,
                                            ),
                                          ),
                                          const SizedBox(height: 4),
                                          Text(
                                            comment.text,
                                            style:
                                                const TextStyle(height: 1.45),
                                          ),
                                        ],
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            );
                          },
                        ),
            ),
            Container(
              padding: EdgeInsets.fromLTRB(
                14,
                10,
                14,
                10 + MediaQuery.viewInsetsOf(context).bottom,
              ),
              decoration: const BoxDecoration(
                color: TimeEchoColors.surface,
                border: Border(top: BorderSide(color: Color(0x12000000))),
              ),
              child: Row(
                children: [
                  Expanded(
                    child: TextField(
                      controller: _input,
                      maxLength: 500,
                      maxLines: 4,
                      minLines: 1,
                      decoration: const InputDecoration(
                        hintText: '友善地说点什么…',
                        counterText: '',
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  IconButton.filled(
                    onPressed: _sending ? null : _send,
                    icon: _sending
                        ? const SizedBox(
                            width: 18,
                            height: 18,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Icon(Icons.send_rounded),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _LoadState extends StatelessWidget {
  const _LoadState({
    required this.icon,
    required this.title,
    required this.message,
    required this.actionLabel,
    required this.onAction,
  });
  final IconData icon;
  final String title;
  final String message;
  final String actionLabel;
  final VoidCallback onAction;

  @override
  Widget build(BuildContext context) => Center(
        child: Padding(
          padding: const EdgeInsets.all(30),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(icon, size: 54, color: TimeEchoColors.duskPurple),
              const SizedBox(height: 14),
              Text(
                title,
                style:
                    const TextStyle(fontWeight: FontWeight.w900, fontSize: 20),
              ),
              const SizedBox(height: 8),
              Text(
                message,
                textAlign: TextAlign.center,
                style:
                    const TextStyle(color: TimeEchoColors.muted, height: 1.5),
              ),
              const SizedBox(height: 18),
              FilledButton.tonal(onPressed: onAction, child: Text(actionLabel)),
            ],
          ),
        ),
      );
}
