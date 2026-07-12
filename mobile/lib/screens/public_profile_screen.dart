import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../core/app_config.dart';
import '../core/theme.dart';
import '../core/unread_controller.dart';
import '../models/social.dart';
import '../services/chat_service.dart';
import '../services/social_service.dart';
import '../widgets/social_avatar.dart';
import '../widgets/timeecho_card.dart';
import 'chat_screen.dart';
import 'social_media_viewer_screen.dart';

class PublicProfileScreen extends StatefulWidget {
  const PublicProfileScreen({super.key, required this.userId});

  final int userId;

  @override
  State<PublicProfileScreen> createState() => _PublicProfileScreenState();
}

class _PublicProfileScreenState extends State<PublicProfileScreen> {
  final _social = SocialService();
  final _chat = ChatService();
  PublicUserProfile? _profile;
  List<SocialPost> _posts = const [];
  bool _loading = true;
  bool _postsLoading = false;
  bool _acting = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load({bool forceRefresh = false}) async {
    if (mounted) {
      setState(() {
        _loading = true;
        _error = null;
      });
    }
    try {
      final values = await Future.wait([
        _social.publicProfile(widget.userId, forceRefresh: forceRefresh),
        _social.posts(
          authorId: widget.userId,
          pageSize: 20,
          forceRefresh: forceRefresh,
        ),
      ]);
      final profile = values[0] as PublicUserProfile;
      final posts = values[1] as List<SocialPost>;
      if (!mounted) return;
      setState(() {
        _profile = profile;
        _posts = posts;
        _loading = false;
        _postsLoading = false;
      });
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) {
        setState(() {
          _loading = false;
          _postsLoading = false;
        });
      }
    }
  }

  Future<void> _sendFriendRequest() async {
    setState(() => _acting = true);
    try {
      await _social.sendFriendRequest(widget.userId);
      if (!mounted || _profile == null) return;
      setState(
        () => _profile = _profile!.copyWith(
          relationship: 'OUTGOING_PENDING',
          isFriend: false,
          canMessage: false,
        ),
      );
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('好友申请已发送')));
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(error.toString())));
      }
    } finally {
      if (mounted) setState(() => _acting = false);
    }
  }

  Future<void> _handleIncoming(bool accept) async {
    final requestId = _profile?.pendingRequestId;
    if (requestId == null) return;
    setState(() => _acting = true);
    try {
      await _social.handleFriendRequest(requestId, accept: accept);
      if (!mounted || _profile == null) return;
      setState(
        () => _profile = _profile!.copyWith(
          relationship: accept ? 'FRIEND' : 'NONE',
          isFriend: accept,
          canMessage: accept,
          friendCount: _profile!.friendCount + (accept ? 1 : 0),
          clearPendingRequest: true,
        ),
      );
      await UnreadController.instance.refresh();
      if (!mounted) return;
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(accept ? '已添加为好友' : '已拒绝好友申请')));
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(error.toString())));
      }
    } finally {
      if (mounted) setState(() => _acting = false);
    }
  }

  Future<void> _message() async {
    setState(() => _acting = true);
    try {
      final room = await _chat.createFriendRoom(widget.userId);
      if (!mounted) return;
      await Navigator.push(
        context,
        MaterialPageRoute(
          builder: (_) => ChatScreen(
            args: ChatScreenArgs(
              roomId: room.roomId,
              peerName: room.peerAnonymousName ?? _profile?.displayName,
              isTemporary: false,
            ),
          ),
        ),
      );
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(error.toString())));
      }
    } finally {
      if (mounted) setState(() => _acting = false);
    }
  }

  Future<void> _removeFriend() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('删除好友？'),
        content: const Text('删除后将不能继续发送好友私信，也看不到仅好友可见的动态。'),
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
    setState(() => _acting = true);
    try {
      await _social.removeFriend(widget.userId);
      if (!mounted || _profile == null) return;
      setState(
        () => _profile = _profile!.copyWith(
          relationship: 'NONE',
          isFriend: false,
          canMessage: false,
          friendCount: (_profile!.friendCount - 1).clamp(0, 1 << 31).toInt(),
        ),
      );
      await _load();
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(error.toString())));
      }
    } finally {
      if (mounted) setState(() => _acting = false);
    }
  }

  Future<void> _setRemark() async {
    final profile = _profile;
    if (profile == null || !profile.isFriend) return;
    final controller = TextEditingController(text: profile.remark ?? '');
    final value = await showDialog<String?>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('好友备注'),
        content: TextField(
          controller: controller,
          autofocus: true,
          maxLength: 40,
          decoration: const InputDecoration(hintText: '输入备注名'),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('取消'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context, ''),
            child: const Text('清除'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, controller.text),
            child: const Text('保存'),
          ),
        ],
      ),
    );
    controller.dispose();
    if (value == null || !mounted) return;
    try {
      final remark = await _social.setFriendRemark(widget.userId, value);
      if (!mounted || _profile == null) return;
      final fallback = _profile!.username ?? _profile!.displayName;
      setState(
        () => _profile = _profile!.copyWith(
          remark: remark,
          displayName: remark?.isNotEmpty == true ? remark : fallback,
          clearRemark: remark == null,
        ),
      );
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(error.toString())));
      }
    }
  }

  Future<void> _reportUser() async {
    const reasons = ['骚扰或辱骂', '垃圾广告', '冒充他人', '不当内容', '其他'];
    var selected = reasons.first;
    final description = TextEditingController();
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setDialogState) => AlertDialog(
          title: const Text('举报用户'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              DropdownButtonFormField<String>(
                initialValue: selected,
                items: reasons
                    .map(
                      (item) =>
                          DropdownMenuItem(value: item, child: Text(item)),
                    )
                    .toList(),
                onChanged: (value) {
                  if (value != null) {
                    setDialogState(() => selected = value);
                  }
                },
              ),
              const SizedBox(height: 12),
              TextField(
                controller: description,
                maxLength: 300,
                maxLines: 3,
                decoration: const InputDecoration(hintText: '补充说明（可选）'),
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('取消'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(context, true),
              child: const Text('提交'),
            ),
          ],
        ),
      ),
    );
    if (confirmed != true) {
      description.dispose();
      return;
    }
    try {
      await _social.reportUser(
        widget.userId,
        reason: selected,
        description: description.text,
      );
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(const SnackBar(content: Text('举报已提交')));
      }
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(error.toString())));
      }
    } finally {
      description.dispose();
    }
  }

  Future<void> _blockUser() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('拉黑该用户？'),
        content: const Text('拉黑后将解除好友关系，双方不能再匹配、互动或私信。'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('取消'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('拉黑'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    try {
      await _social.blockUser(widget.userId);
      if (mounted) Navigator.pop(context, true);
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(error.toString())));
      }
    }
  }

  void _profileAction(String action) {
    if (action == 'remark') {
      _setRemark();
    } else if (action == 'report') {
      _reportUser();
    } else if (action == 'block') {
      _blockUser();
    }
  }

  Future<void> _deletePost(SocialPost post) async {
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
    await _social.deletePost(post.id);
    if (mounted) {
      setState(
        () => _posts = _posts.where((item) => item.id != post.id).toList(),
      );
    }
  }

  Widget _relationshipActions(PublicUserProfile profile) {
    if (profile.isMe) return const SizedBox.shrink();
    if (_acting) {
      return const Padding(
        padding: EdgeInsets.symmetric(vertical: 10),
        child: Center(child: CircularProgressIndicator(strokeWidth: 2)),
      );
    }
    switch (profile.relationship) {
      case 'FRIEND':
        return Row(
          children: [
            Expanded(
              child: FilledButton.icon(
                onPressed: _message,
                icon: const Icon(Icons.chat_bubble_outline_rounded),
                label: const Text('发私信'),
              ),
            ),
            const SizedBox(width: 10),
            IconButton.outlined(
              onPressed: _removeFriend,
              tooltip: '删除好友',
              icon: const Icon(Icons.person_remove_outlined),
            ),
          ],
        );
      case 'INCOMING_PENDING':
        return Row(
          children: [
            Expanded(
              child: OutlinedButton(
                onPressed: () => _handleIncoming(false),
                child: const Text('拒绝'),
              ),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: FilledButton(
                onPressed: () => _handleIncoming(true),
                child: const Text('通过申请'),
              ),
            ),
          ],
        );
      case 'OUTGOING_PENDING':
        return const FilledButton.tonal(
          onPressed: null,
          child: Text('好友申请已发送'),
        );
      default:
        return FilledButton.icon(
          onPressed: _sendFriendRequest,
          icon: const Icon(Icons.person_add_alt_1_rounded),
          label: const Text('添加好友'),
        );
    }
  }

  String _absoluteUrl(String path) => path.startsWith('http')
      ? path
      : '${AppConfig.apiBaseUrl}${path.startsWith('/') ? '' : '/'}$path';

  @override
  Widget build(BuildContext context) {
    final profile = _profile;
    return Scaffold(
      appBar: AppBar(
        title: Text(profile?.displayName ?? '个人主页'),
        actions: [
          if (profile != null && !profile.isMe)
            PopupMenuButton<String>(
              onSelected: _profileAction,
              itemBuilder: (_) => [
                if (profile.isFriend)
                  const PopupMenuItem(value: 'remark', child: Text('设置备注')),
                const PopupMenuItem(value: 'report', child: Text('举报')),
                const PopupMenuDivider(),
                const PopupMenuItem(value: 'block', child: Text('拉黑')),
              ],
            ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: () => _load(forceRefresh: true),
        child: _loading && _profile == null
            ? ListView(
                children: const [
                  SizedBox(height: 260),
                  Center(child: CircularProgressIndicator()),
                ],
              )
            : _error != null
                ? ListView(
                    padding: const EdgeInsets.all(24),
                    children: [
                      const SizedBox(height: 120),
                      Text(_error!, textAlign: TextAlign.center),
                      const SizedBox(height: 12),
                      FilledButton.tonal(
                        onPressed: _load,
                        child: const Text('重新加载'),
                      ),
                    ],
                  )
                : ListView(
                    padding: const EdgeInsets.fromLTRB(16, 12, 16, 40),
                    children: [
                      if (_profile != null) _profileCard(_profile!),
                      const SizedBox(height: 18),
                      Row(
                        children: [
                          const Text(
                            '动态',
                            style: TextStyle(
                              fontSize: 19,
                              fontWeight: FontWeight.w900,
                            ),
                          ),
                          const Spacer(),
                          Text(
                            '${_posts.length} 条',
                            style: const TextStyle(color: TimeEchoColors.muted),
                          ),
                        ],
                      ),
                      const SizedBox(height: 10),
                      if (_postsLoading)
                        const LinearProgressIndicator(minHeight: 2),
                      if (_posts.isEmpty)
                        const TimeEchoCard(
                          child: Padding(
                            padding: EdgeInsets.symmetric(vertical: 20),
                            child: Text(
                              '这里暂时没有你可以查看的动态。',
                              textAlign: TextAlign.center,
                            ),
                          ),
                        )
                      else
                        ..._posts.map(_postCard),
                    ],
                  ),
      ),
    );
  }

  Widget _profileCard(PublicUserProfile profile) => TimeEchoCard(
        padding: const EdgeInsets.all(20),
        child: Column(
          children: [
            SocialAvatar(
              name: profile.displayName,
              url: profile.avatarUrl,
              radius: 44,
            ),
            const SizedBox(height: 12),
            Text(
              profile.displayName,
              style: const TextStyle(fontSize: 23, fontWeight: FontWeight.w900),
            ),
            if (profile.uid != null) ...[
              const SizedBox(height: 3),
              Text(
                'UID ${profile.uid}',
                style: const TextStyle(
                  color: TimeEchoColors.muted,
                  fontSize: 13,
                ),
              ),
            ],
            if (profile.bio?.trim().isNotEmpty == true) ...[
              const SizedBox(height: 7),
              Text(
                profile.bio!,
                textAlign: TextAlign.center,
                style: const TextStyle(height: 1.45),
              ),
            ],
            const SizedBox(height: 16),
            Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                _ProfileStat(value: '${profile.friendCount}', label: '好友'),
                const SizedBox(width: 36),
                _ProfileStat(value: '${profile.postCount}', label: '动态'),
              ],
            ),
            const SizedBox(height: 16),
            SizedBox(
                width: double.infinity, child: _relationshipActions(profile)),
          ],
        ),
      );

  Widget _postCard(SocialPost post) => Padding(
        padding: const EdgeInsets.only(bottom: 12),
        child: TimeEchoCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Text(
                    DateFormat('yyyy-MM-dd HH:mm')
                        .format(post.createdAt.toLocal()),
                  ),
                  const Spacer(),
                  if (post.isMine)
                    PopupMenuButton<String>(
                      tooltip: '动态操作',
                      onSelected: (value) {
                        if (value == 'delete') _deletePost(post);
                      },
                      itemBuilder: (_) => const [
                        PopupMenuItem(value: 'delete', child: Text('删除动态')),
                      ],
                    ),
                ],
              ),
              if (post.text.isNotEmpty) ...[
                const SizedBox(height: 10),
                Text(post.text,
                    style: const TextStyle(fontSize: 16, height: 1.5)),
              ],
              if (post.media.isNotEmpty) ...[
                const SizedBox(height: 10),
                _ProfileMedia(media: post.media, absoluteUrl: _absoluteUrl),
              ],
              const SizedBox(height: 10),
              Text(
                '喜欢 ${post.likeCount} · 评论 ${post.commentCount}',
                style: const TextStyle(color: TimeEchoColors.muted),
              ),
            ],
          ),
        ),
      );
}

class _ProfileStat extends StatelessWidget {
  const _ProfileStat({required this.value, required this.label});
  final String value;
  final String label;

  @override
  Widget build(BuildContext context) => Column(
        children: [
          Text(
            value,
            style: const TextStyle(fontSize: 19, fontWeight: FontWeight.w900),
          ),
          Text(
            label,
            style: const TextStyle(fontSize: 12, color: TimeEchoColors.muted),
          ),
        ],
      );
}

class _ProfileMedia extends StatelessWidget {
  const _ProfileMedia({required this.media, required this.absoluteUrl});
  final List<SocialMedia> media;
  final String Function(String) absoluteUrl;

  @override
  Widget build(BuildContext context) {
    final first = media.first;
    if (first.kind != 'image') {
      return ListTile(
        tileColor: TimeEchoColors.mistBlue,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
        leading: Icon(
          first.kind == 'video'
              ? Icons.play_circle_outline_rounded
              : Icons.graphic_eq_rounded,
        ),
        title: Text(first.kind == 'video' ? '视频动态' : '语音动态'),
      );
    }
    return GridView.builder(
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      itemCount: media.length,
      gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount: media.length == 1 ? 1 : 3,
        crossAxisSpacing: 5,
        mainAxisSpacing: 5,
      ),
      itemBuilder: (context, index) {
        final url = absoluteUrl(media[index].url);
        return GestureDetector(
          onTap: () => Navigator.push(
            context,
            MaterialPageRoute(
              builder: (_) => SocialMediaViewerScreen(media: media[index]),
            ),
          ),
          child: ClipRRect(
            borderRadius: BorderRadius.circular(12),
            child: CachedNetworkImage(imageUrl: url, fit: BoxFit.cover),
          ),
        );
      },
    );
  }
}
