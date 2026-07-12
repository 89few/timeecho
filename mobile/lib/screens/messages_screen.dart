import 'dart:async';

import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../core/theme.dart';
import '../core/unread_controller.dart';
import '../models/chat_room.dart';
import '../models/social.dart';
import '../services/chat_service.dart';
import '../services/social_service.dart';
import '../widgets/social_avatar.dart';
import '../widgets/timeecho_card.dart';
import 'chat_screen.dart';
import 'friends_screen.dart';
import 'public_profile_screen.dart';
import 'post_detail_screen.dart';

class MessagesScreen extends StatefulWidget {
  const MessagesScreen({super.key});

  @override
  State<MessagesScreen> createState() => _MessagesScreenState();
}

class _MessagesScreenState extends State<MessagesScreen> {
  final _chat = ChatService();
  final _social = SocialService();
  List<ChatRoomInfo> _rooms = const [];
  List<SocialNotification> _notifications = const [];
  List<FriendRequestInfo> _pendingRequests = const [];
  int _unreadNotificationCount = 0;
  bool _loading = true;
  String? _error;
  Timer? _refreshTimer;

  @override
  void initState() {
    super.initState();
    _load();
    _refreshTimer = Timer.periodic(
      const Duration(seconds: 20),
      (_) => _load(showLoading: false, forceRefresh: true),
    );
  }

  @override
  void dispose() {
    _refreshTimer?.cancel();
    super.dispose();
  }

  Future<void> _load({
    bool showLoading = true,
    bool forceRefresh = false,
  }) async {
    if (mounted && showLoading && _rooms.isEmpty && _notifications.isEmpty) {
      setState(() {
        _loading = true;
        _error = null;
      });
    }
    try {
      final overview = await _social.messageOverview();
      if (!mounted) return;
      final rooms = overview.rooms;
      final notifications = overview.notifications;
      final notificationCount =
          notifications.where((item) => !item.isRead).length;
      setState(() {
        _rooms = rooms;
        _notifications = notifications;
        _pendingRequests = overview.friendRequests;
        _unreadNotificationCount = notificationCount;
        _error = null;
      });
      UnreadController.instance.update(
        notificationCount: notificationCount,
        chatCount: rooms.fold<int>(0, (sum, room) => sum + room.unreadCount),
      );
    } catch (error) {
      if (mounted && _rooms.isEmpty && _notifications.isEmpty) {
        setState(() => _error = error.toString());
      }
    } finally {
      if (mounted && showLoading) setState(() => _loading = false);
    }
  }

  Future<void> _markAllRead() async {
    try {
      await _social.markAllNotificationsRead();
      if (!mounted) return;
      setState(() {
        _notifications =
            _notifications.map((item) => item.copyWith(isRead: true)).toList();
        _unreadNotificationCount = 0;
      });
      _syncUnread();
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(error.toString())));
      }
    }
  }

  Future<void> _openNotification(SocialNotification notification) async {
    if (!notification.isRead) {
      try {
        await _social.markNotificationRead(notification.id);
        if (mounted) {
          setState(() {
            _notifications = _notifications
                .map(
                  (item) => item.id == notification.id
                      ? item.copyWith(isRead: true)
                      : item,
                )
                .toList();
            _unreadNotificationCount =
                (_unreadNotificationCount - 1).clamp(0, 1 << 31).toInt();
          });
          _syncUnread();
        }
      } catch (_) {
        // Navigation remains available even if marking read briefly fails.
      }
    }
    if (!mounted) return;
    if (notification.type == 'FRIEND_REQUEST') {
      await Navigator.push(
        context,
        MaterialPageRoute(builder: (_) => const FriendsScreen()),
      );
    } else if (notification.type == 'CARD_EXCHANGE') {
      final roomId = int.tryParse('${notification.data['room_id'] ?? ''}');
      if (roomId != null) {
        try {
          final room = await _chat.roomStatus(roomId);
          if (!mounted) return;
          await Navigator.pushNamed(
            context,
            '/chat',
            arguments: ChatScreenArgs(
              roomId: room.roomId,
              peerName: room.peerAnonymousName,
              isTemporary: true,
              roomKind: room.roomKind,
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
    } else if (notification.type == 'POST_LIKE' ||
        notification.type == 'POST_COMMENT') {
      final postId = int.tryParse('${notification.data['post_id'] ?? ''}');
      if (postId != null) {
        await Navigator.push(
          context,
          MaterialPageRoute(builder: (_) => PostDetailScreen(postId: postId)),
        );
      }
    } else if (notification.actor != null) {
      await Navigator.push(
        context,
        MaterialPageRoute(
          builder: (_) => PublicProfileScreen(userId: notification.actor!.id),
        ),
      );
    }
    if (mounted) _load(showLoading: false);
  }

  Future<void> _openFriends() async {
    await Navigator.push(
      context,
      MaterialPageRoute(builder: (_) => const FriendsScreen(initialTab: 1)),
    );
    if (mounted) await _load(showLoading: false);
  }

  Future<void> _openNotificationGroup(
    String title,
    List<SocialNotification> items,
  ) async {
    await showModalBottomSheet<void>(
      context: context,
      useSafeArea: true,
      isScrollControlled: true,
      builder: (sheetContext) => DraggableScrollableSheet(
        expand: false,
        initialChildSize: .72,
        maxChildSize: .94,
        builder: (_, controller) => Column(
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 18, 12, 8),
              child: Row(
                children: [
                  Text(
                    title,
                    style: const TextStyle(
                      fontSize: 20,
                      fontWeight: FontWeight.w900,
                    ),
                  ),
                  const Spacer(),
                  IconButton(
                    onPressed: () => Navigator.pop(sheetContext),
                    icon: const Icon(Icons.close_rounded),
                  ),
                ],
              ),
            ),
            Expanded(
              child: ListView(
                controller: controller,
                padding: const EdgeInsets.fromLTRB(14, 4, 14, 24),
                children: items.map(_notificationCard).toList(),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _openRoom(ChatRoomInfo room) async {
    await Navigator.pushNamed(
      context,
      '/chat',
      arguments: ChatScreenArgs(
        roomId: room.roomId,
        peerName: room.peerAnonymousName,
        isTemporary: room.isTemporary,
      ),
    );
    if (mounted) _load(showLoading: false);
  }

  @override
  Widget build(BuildContext context) {
    final directRooms = _rooms.where((room) => !room.isTemporary).toList();
    final temporaryRooms = _rooms.where((room) => room.isTemporary).toList();
    final unreadNotifications = _unreadNotificationCount;
    final visibleNotifications =
        _notifications.where((item) => item.type != 'FRIEND_REQUEST').toList();
    final likeNotifications =
        visibleNotifications.where((item) => item.type == 'POST_LIKE').toList();
    final commentNotifications = visibleNotifications
        .where((item) => item.type == 'POST_COMMENT')
        .toList();
    final friendNotifications = visibleNotifications
        .where(
          (item) =>
              item.type == 'FRIEND_ACCEPTED' || item.type == 'FRIEND_REJECTED',
        )
        .toList();
    final sessionNotifications = visibleNotifications
        .where((item) => item.type == 'CARD_EXCHANGE')
        .toList();

    return RefreshIndicator(
      onRefresh: () => _load(showLoading: false, forceRefresh: true),
      child: ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.fromLTRB(18, 18, 18, 110),
        children: [
          Row(
            children: [
              Text(
                '消息',
                style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                      fontWeight: FontWeight.w900,
                    ),
              ),
              const Spacer(),
              if (unreadNotifications > 0)
                TextButton(
                  onPressed: _markAllRead,
                  child: Text('全部已读 ($unreadNotifications)'),
                ),
            ],
          ),
          const SizedBox(height: 12),
          if (_loading && _rooms.isEmpty && _notifications.isEmpty)
            const Padding(
              padding: EdgeInsets.only(top: 80),
              child: Center(child: CircularProgressIndicator()),
            ),
          if (_error != null) TimeEchoCard(child: Text(_error!)),
          if (!_loading &&
              _rooms.isEmpty &&
              visibleNotifications.isEmpty &&
              _pendingRequests.isEmpty)
            const TimeEchoCard(child: Text('还没有消息或通知。')),
          if (!_loading) ...[_newFriendsCard(), const SizedBox(height: 14)],
          if (visibleNotifications.isNotEmpty) ...[
            TimeEchoCard(
              padding: EdgeInsets.zero,
              child: Column(
                children: [
                  if (likeNotifications.isNotEmpty)
                    _notificationGroupTile(
                      '赞',
                      Icons.favorite_outline_rounded,
                      likeNotifications,
                    ),
                  if (commentNotifications.isNotEmpty)
                    _notificationGroupTile(
                      '评论',
                      Icons.chat_bubble_outline_rounded,
                      commentNotifications,
                    ),
                  if (friendNotifications.isNotEmpty)
                    _notificationGroupTile(
                      '好友通知',
                      Icons.people_outline_rounded,
                      friendNotifications,
                    ),
                  if (sessionNotifications.isNotEmpty)
                    _notificationGroupTile(
                      '会话通知',
                      Icons.badge_outlined,
                      sessionNotifications,
                    ),
                ],
              ),
            ),
            const SizedBox(height: 14),
          ],
          if (directRooms.isNotEmpty) ...[
            _sectionTitle('好友私信'),
            const SizedBox(height: 8),
            ...directRooms.map(_roomCard),
            const SizedBox(height: 8),
          ],
          if (temporaryRooms.isNotEmpty) ...[
            _sectionTitle('临时回信'),
            const SizedBox(height: 8),
            ...temporaryRooms.map(_roomCard),
          ],
        ],
      ),
    );
  }

  Widget _sectionTitle(String title, {int count = 0}) => Row(
        children: [
          Text(
            title,
            style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w900),
          ),
          if (count > 0) ...[
            const SizedBox(width: 6),
            Badge(label: Text('$count')),
          ],
        ],
      );

  Widget _newFriendsCard() => TimeEchoCard(
        padding: EdgeInsets.zero,
        child: ListTile(
          onTap: _openFriends,
          contentPadding:
              const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
          leading: Badge(
            isLabelVisible: _pendingRequests.isNotEmpty,
            label: Text(
              _pendingRequests.length > 99
                  ? '99+'
                  : '${_pendingRequests.length}',
            ),
            child: const CircleAvatar(
              backgroundColor: Color(0xFFE7DDF2),
              child: Icon(
                Icons.person_add_alt_1_rounded,
                color: TimeEchoColors.duskPurple,
              ),
            ),
          ),
          title:
              const Text('新的朋友', style: TextStyle(fontWeight: FontWeight.w800)),
          subtitle: _pendingRequests.isEmpty
              ? null
              : Text('${_pendingRequests.length} 个待处理'),
          trailing: const Icon(Icons.chevron_right_rounded),
        ),
      );

  Widget _notificationGroupTile(
    String title,
    IconData icon,
    List<SocialNotification> items,
  ) {
    final unread = items.where((item) => !item.isRead).length;
    return ListTile(
      onTap: () => _openNotificationGroup(title, items),
      leading: CircleAvatar(
        backgroundColor: const Color(0xFFEDE7F2),
        child: Icon(icon, color: TimeEchoColors.duskPurple),
      ),
      title: Text(title, style: const TextStyle(fontWeight: FontWeight.w800)),
      subtitle: Text('${items.length} 条'),
      trailing: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (unread > 0) Badge(label: Text('$unread')),
          const SizedBox(width: 4),
          const Icon(Icons.chevron_right_rounded),
        ],
      ),
    );
  }

  Widget _notificationCard(SocialNotification notification) => Padding(
        padding: const EdgeInsets.only(bottom: 9),
        child: TimeEchoCard(
          padding: EdgeInsets.zero,
          child: ListTile(
            onTap: () => _openNotification(notification),
            contentPadding:
                const EdgeInsets.symmetric(horizontal: 14, vertical: 7),
            leading: Stack(
              clipBehavior: Clip.none,
              children: [
                notification.actor == null
                    ? const CircleAvatar(
                        child: Icon(Icons.notifications_outlined))
                    : SocialAvatar(
                        name: notification.actor!.displayName,
                        url: notification.actor!.avatarUrl,
                      ),
                if (!notification.isRead)
                  const Positioned(
                    right: -1,
                    top: -1,
                    child: CircleAvatar(
                      radius: 5,
                      backgroundColor: Color(0xFFCC6677),
                    ),
                  ),
              ],
            ),
            title: Text(
              notification.actor?.displayName ?? notification.title,
              style: const TextStyle(fontWeight: FontWeight.w800),
            ),
            subtitle: Text(
              switch (notification.type) {
                'POST_LIKE' => '赞了你的动态',
                'POST_COMMENT' => '评论了你的动态',
                'FRIEND_ACCEPTED' => '已成为好友',
                'FRIEND_REJECTED' => '好友申请未通过',
                _ => notification.title,
              },
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
            ),
            trailing: Text(
              _time(notification.createdAt),
              style: const TextStyle(fontSize: 11, color: TimeEchoColors.muted),
            ),
          ),
        ),
      );

  Widget _roomCard(ChatRoomInfo room) => Padding(
        padding: const EdgeInsets.only(bottom: 10),
        child: TimeEchoCard(
          padding: EdgeInsets.zero,
          child: ListTile(
            contentPadding:
                const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            leading: room.isTemporary
                ? CircleAvatar(
                    child:
                        Text((room.peerAnonymousName ?? '回').substring(0, 1)),
                  )
                : SocialAvatar(
                    name: room.peerAnonymousName ?? '好友',
                    url: room.peerAvatarUrl,
                  ),
            title: Text(
              room.peerAnonymousName ?? '匿名回声',
              style: const TextStyle(fontWeight: FontWeight.w800),
            ),
            subtitle: Text(
              room.lastMessage ?? '',
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
            trailing: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                if (room.lastMessageAt != null)
                  Text(
                    _time(room.lastMessageAt!),
                    style: const TextStyle(fontSize: 11),
                  ),
                if (room.unreadCount > 0)
                  Badge(label: Text('${room.unreadCount}')),
              ],
            ),
            onTap: () => _openRoom(room),
          ),
        ),
      );

  String _time(DateTime raw) {
    final time = raw.toLocal();
    final now = DateTime.now();
    if (now.difference(time).inDays == 0) {
      return DateFormat('HH:mm').format(time);
    }
    return DateFormat('MM-dd').format(time);
  }

  void _syncUnread() {
    UnreadController.instance.update(
      notificationCount: _unreadNotificationCount,
      chatCount: _rooms.fold<int>(0, (sum, room) => sum + room.unreadCount),
    );
  }

}
