import 'dart:async';

import 'package:flutter/material.dart';

import '../core/theme.dart';
import '../core/unread_controller.dart';
import '../models/social.dart';
import '../services/chat_service.dart';
import '../services/social_service.dart';
import '../widgets/social_avatar.dart';
import '../widgets/timeecho_card.dart';
import 'chat_screen.dart';
import 'public_profile_screen.dart';

class FriendsScreen extends StatefulWidget {
  const FriendsScreen({super.key, this.initialTab = 0});

  final int initialTab;

  @override
  State<FriendsScreen> createState() => _FriendsScreenState();
}

class _FriendsScreenState extends State<FriendsScreen>
    with SingleTickerProviderStateMixin {
  late final TabController _tabController;
  final _service = SocialService();
  final _chat = ChatService();
  final _search = TextEditingController();
  Timer? _debounce;
  List<SocialUser> _friends = const [];
  List<FriendRequestInfo> _requests = const [];
  List<SocialUser> _results = const [];
  bool _loading = true;
  bool _searching = false;
  String? _error;
  final Set<int> _handlingRequestIds = <int>{};

  @override
  void initState() {
    super.initState();
    _tabController = TabController(
      length: 3,
      vsync: this,
      initialIndex: widget.initialTab.clamp(0, 2),
    );
    _load();
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _tabController.dispose();
    _search.dispose();
    super.dispose();
  }

  Future<void> _load({bool forceRefresh = false}) async {
    if (mounted) {
      setState(() {
        if (_friends.isEmpty && _requests.isEmpty) _loading = true;
        _error = null;
      });
    }
    try {
      final values = await Future.wait([
        _service.friends(forceRefresh: forceRefresh),
        _service.friendRequests(forceRefresh: forceRefresh),
      ]);
      if (!mounted) return;
      setState(() {
        _friends = values[0] as List<SocialUser>;
        _requests = values[1] as List<FriendRequestInfo>;
      });
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  void _scheduleSearch(String value) {
    _debounce?.cancel();
    if (value.trim().isEmpty) {
      setState(() => _results = const []);
      return;
    }
    _debounce = Timer(
      const Duration(milliseconds: 450),
      () => _runSearch(value),
    );
  }

  Future<void> _runSearch(String value) async {
    setState(() {
      _searching = true;
      _error = null;
    });
    try {
      final results = await _service.searchUsers(value);
      if (mounted && value == _search.text) setState(() => _results = results);
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _searching = false);
    }
  }

  Future<void> _requestFriend(SocialUser user) async {
    final note = TextEditingController();
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text('添加 ${user.displayName}'),
        content: TextField(
          controller: note,
          maxLength: 80,
          minLines: 2,
          maxLines: 3,
          decoration: const InputDecoration(
            labelText: '验证消息（可选）',
            hintText: '你好，想和你成为朋友',
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('取消'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('发送申请'),
          ),
        ],
      ),
    );
    final message = note.text;
    note.dispose();
    if (confirmed != true) return;
    try {
      await _service.sendFriendRequest(user.id, message: message);
      if (!mounted) return;
      setState(() {
        _results = _results
            .map(
              (item) => item.id == user.id
                  ? item.copyWith(relationship: 'OUTGOING_PENDING')
                  : item,
            )
            .toList();
      });
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('好友申请已发送')));
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(error.toString())));
      }
    }
  }

  Future<void> _handleRequest(FriendRequestInfo request, bool accept) async {
    if (_handlingRequestIds.contains(request.id)) return;
    setState(() => _handlingRequestIds.add(request.id));
    try {
      await _service.handleFriendRequest(request.id, accept: accept);
      if (!mounted) return;
      setState(
        () => _requests =
            _requests.where((item) => item.id != request.id).toList(),
      );
      if (accept) {
        final friends = await _service.friends(forceRefresh: true);
        if (!mounted) return;
        setState(() => _friends = friends);
      }
      await UnreadController.instance.refresh();
      if (!mounted) return;
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(accept ? '已添加为好友' : '已忽略申请')));
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(error.toString())));
      }
    } finally {
      if (mounted) setState(() => _handlingRequestIds.remove(request.id));
    }
  }

  Future<void> _messageFriend(SocialUser friend) async {
    try {
      final room = await _chat.createFriendRoom(friend.id);
      if (!mounted) return;
      await Navigator.push(
        context,
        MaterialPageRoute(
          builder: (_) => ChatScreen(
            args: ChatScreenArgs(
              roomId: room.roomId,
              peerName: friend.displayName,
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
    }
  }

  Future<void> _openProfile(int userId) async {
    await Navigator.push(
      context,
      MaterialPageRoute(builder: (_) => PublicProfileScreen(userId: userId)),
    );
    if (mounted) _load(forceRefresh: true);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('好友'),
        bottom: TabBar(
          controller: _tabController,
          tabs: [
            Tab(text: '好友 ${_friends.isEmpty ? '' : _friends.length}'),
            Tab(text: '新的朋友 ${_requests.isEmpty ? '' : _requests.length}'),
            const Tab(text: '找人'),
          ],
        ),
      ),
      body: SafeArea(
        child: _loading && _friends.isEmpty && _requests.isEmpty
            ? const Center(child: CircularProgressIndicator())
            : TabBarView(
                controller: _tabController,
                children: [_friendsTab(), _requestsTab(), _searchTab()],
              ),
      ),
    );
  }

  Widget _friendsTab() {
    if (_friends.isEmpty) {
      return const _FriendsEmpty(
        icon: Icons.people_outline_rounded,
        title: '还没有好友',
        message: '可以在“找人”中搜索用户。',
      );
    }
    return RefreshIndicator(
      onRefresh: () => _load(forceRefresh: true),
      child: ListView.separated(
        padding: const EdgeInsets.all(16),
        itemCount: _friends.length,
        separatorBuilder: (_, __) => const SizedBox(height: 8),
        itemBuilder: (context, index) {
          final friend = _friends[index];
          return TimeEchoCard(
            padding: EdgeInsets.zero,
            child: ListTile(
              onTap: () => _openProfile(friend.id),
              contentPadding: const EdgeInsets.symmetric(
                horizontal: 14,
                vertical: 6,
              ),
              leading: SocialAvatar(
                name: friend.displayName,
                url: friend.avatarUrl,
              ),
              title: Text(
                friend.displayName,
                style: const TextStyle(fontWeight: FontWeight.w800),
              ),
              subtitle: friend.bio?.trim().isNotEmpty == true
                  ? Text(
                      friend.bio!,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    )
                  : null,
              trailing: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  IconButton(
                    tooltip: '发私信',
                    onPressed: () => _messageFriend(friend),
                    icon: const Icon(Icons.chat_bubble_outline_rounded),
                  ),
                  const Icon(Icons.chevron_right_rounded),
                ],
              ),
            ),
          );
        },
      ),
    );
  }

  Widget _requestsTab() {
    if (_requests.isEmpty) {
      return const _FriendsEmpty(
        icon: Icons.person_add_alt_1_outlined,
        title: '没有新的好友申请',
        message: '',
      );
    }
    return RefreshIndicator(
      onRefresh: () => _load(forceRefresh: true),
      child: ListView.separated(
        padding: const EdgeInsets.all(16),
        itemCount: _requests.length,
        separatorBuilder: (_, __) => const SizedBox(height: 8),
        itemBuilder: (context, index) {
          final request = _requests[index];
          return GestureDetector(
            onTap: () => _openProfile(request.user.id),
            child: TimeEchoCard(
              child: Row(
                children: [
                  SocialAvatar(
                    name: request.user.displayName,
                    url: request.user.avatarUrl,
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          request.user.displayName,
                          style: const TextStyle(fontWeight: FontWeight.w800),
                        ),
                        if (request.message?.trim().isNotEmpty == true)
                          Text(
                            request.message!,
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(color: TimeEchoColors.muted),
                          ),
                      ],
                    ),
                  ),
                  IconButton(
                    onPressed: _handlingRequestIds.contains(request.id)
                        ? null
                        : () => _handleRequest(request, false),
                    tooltip: '忽略',
                    icon: const Icon(Icons.close_rounded),
                  ),
                  IconButton.filled(
                    onPressed: _handlingRequestIds.contains(request.id)
                        ? null
                        : () => _handleRequest(request, true),
                    tooltip: '接受',
                    icon: const Icon(Icons.check_rounded),
                  ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }

  Widget _searchTab() {
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
          child: TextField(
            controller: _search,
            autofocus: true,
            textInputAction: TextInputAction.search,
            onChanged: _scheduleSearch,
            onSubmitted: _runSearch,
            decoration: InputDecoration(
              hintText: '搜索 UID、昵称或邮箱',
              prefixIcon: const Icon(Icons.search_rounded),
              suffixIcon: _searching
                  ? const Padding(
                      padding: EdgeInsets.all(14),
                      child: SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      ),
                    )
                  : _search.text.isNotEmpty
                      ? IconButton(
                          onPressed: () => setState(() {
                            _search.clear();
                            _results = const [];
                          }),
                          icon: const Icon(Icons.close_rounded),
                        )
                      : null,
            ),
          ),
        ),
        if (_error != null)
          Padding(
            padding: const EdgeInsets.all(12),
            child: Text(
              _error!,
              style: TextStyle(color: Theme.of(context).colorScheme.error),
            ),
          ),
        Expanded(
          child: _results.isEmpty
              ? const _FriendsEmpty(
                  icon: Icons.travel_explore_rounded,
                  title: '寻找朋友',
                  message: '输入 8 位 UID、邮箱或昵称开始搜索。',
                )
              : ListView.separated(
                  padding: const EdgeInsets.all(16),
                  itemCount: _results.length,
                  separatorBuilder: (_, __) => const Divider(height: 1),
                  itemBuilder: (context, index) {
                    final user = _results[index];
                    return ListTile(
                      onTap: () => _openProfile(user.id),
                      leading: SocialAvatar(
                        name: user.displayName,
                        url: user.avatarUrl,
                      ),
                      title: Text(
                        user.displayName,
                        style: const TextStyle(fontWeight: FontWeight.w700),
                      ),
                      subtitle: Text(
                        [
                          if (user.uid != null) 'UID ${user.uid}',
                          if (user.bio?.trim().isNotEmpty == true) user.bio!,
                        ].join(' · '),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                      trailing: switch (user.relationship) {
                        'FRIEND' => const Chip(label: Text('已是好友')),
                        'OUTGOING_PENDING' => const Chip(label: Text('已申请')),
                        'INCOMING_PENDING' => const Chip(label: Text('待处理')),
                        _ => FilledButton.tonal(
                            onPressed: () => _requestFriend(user),
                            child: const Text('添加'),
                          ),
                      },
                    );
                  },
                ),
        ),
      ],
    );
  }
}

class _FriendsEmpty extends StatelessWidget {
  const _FriendsEmpty({
    required this.icon,
    required this.title,
    required this.message,
  });
  final IconData icon;
  final String title;
  final String message;

  @override
  Widget build(BuildContext context) => Center(
        child: Padding(
          padding: const EdgeInsets.all(30),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(icon, size: 52, color: TimeEchoColors.duskPurple),
              const SizedBox(height: 14),
              Text(
                title,
                style:
                    const TextStyle(fontWeight: FontWeight.w900, fontSize: 19),
              ),
              const SizedBox(height: 6),
              Text(
                message,
                textAlign: TextAlign.center,
                style:
                    const TextStyle(color: TimeEchoColors.muted, height: 1.5),
              ),
            ],
          ),
        ),
      );
}
