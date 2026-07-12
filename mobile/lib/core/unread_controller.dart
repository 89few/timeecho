import 'package:flutter/foundation.dart';

import 'app_notification_service.dart';
import '../models/chat_room.dart';
import '../services/chat_service.dart';
import '../services/social_service.dart';

@immutable
class UnreadState {
  const UnreadState({this.notifications = 0, this.chats = 0});

  final int notifications;
  final int chats;

  int get total => notifications + chats;

  UnreadState copyWith({int? notifications, int? chats}) => UnreadState(
        notifications: notifications ?? this.notifications,
        chats: chats ?? this.chats,
      );
}

/// Keeps the unread badge consistent across the home navigation, message list,
/// friend requests and chat screens. Network refreshes are coalesced so several
/// screens becoming visible at once do not produce duplicate requests.
class UnreadController {
  UnreadController._();

  static final UnreadController instance = UnreadController._();

  final ValueNotifier<UnreadState> state = ValueNotifier<UnreadState>(
    const UnreadState(),
  );
  final SocialService _social = SocialService();
  final ChatService _chat = ChatService();
  Future<void>? _inFlight;
  bool _baselineReady = false;
  Map<int, int> _roomUnread = const {};
  Set<int> _notificationIds = const {};

  Future<void> refresh() {
    final active = _inFlight;
    if (active != null) return active;

    late final Future<void> current;
    current = _refresh().whenComplete(() {
      if (identical(_inFlight, current)) _inFlight = null;
    });
    _inFlight = current;
    return current;
  }

  Future<void> _refresh() async {
    final notificationFuture = _try(_social.unreadNotificationCount());
    final notificationItemsFuture = _try(
      _social.notifications(pageSize: 100, unreadOnly: true),
    );
    final roomsFuture = _try(_chat.rooms());
    final notificationCount = await notificationFuture;
    final notificationItems = await notificationItemsFuture;
    final rooms = await roomsFuture;

    if (_baselineReady) {
      if (rooms != null) {
        for (final room in rooms) {
          final previous = _roomUnread[room.roomId] ?? 0;
          if (room.unreadCount > previous) {
            await AppNotificationService.instance.showChat(room);
          }
        }
      }
      if (notificationItems != null) {
        for (final item in notificationItems) {
          if (!_notificationIds.contains(item.id)) {
            await AppNotificationService.instance.showSocial(item);
          }
        }
      }
    }

    if (rooms != null) {
      _roomUnread = {for (final room in rooms) room.roomId: room.unreadCount};
    }
    if (notificationItems != null) {
      _notificationIds = notificationItems.map((item) => item.id).toSet();
    }
    if (rooms != null || notificationItems != null) _baselineReady = true;

    update(
      notificationCount: notificationCount,
      chatCount: rooms?.fold<int>(
        0,
        (sum, ChatRoomInfo room) => sum + room.unreadCount,
      ),
    );
  }

  void reset() {
    _inFlight = null;
    _baselineReady = false;
    _roomUnread = const {};
    _notificationIds = const {};
    state.value = const UnreadState();
  }

  void update({int? notificationCount, int? chatCount}) {
    final current = state.value;
    final next = UnreadState(
      notifications:
          notificationCount?.clamp(0, 1 << 31).toInt() ?? current.notifications,
      chats: chatCount?.clamp(0, 1 << 31).toInt() ?? current.chats,
    );
    if (next.notifications != current.notifications ||
        next.chats != current.chats) {
      state.value = next;
    }
  }

  Future<T?> _try<T>(Future<T> request) async {
    try {
      return await request;
    } catch (_) {
      // A partial outage must not erase the still-valid count from another
      // endpoint or break the original paper-plane message experience.
      return null;
    }
  }
}
