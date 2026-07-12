import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import '../core/token_store.dart';
import '../core/app_config.dart';
import '../core/theme.dart';
import '../core/unread_controller.dart';
import '../core/app_notification_service.dart';
import '../services/user_service.dart';
import '../services/chat_service.dart';
import '../services/matching_service.dart';
import '../models/chat_room.dart';
import '../models/matching.dart';
import '../widgets/timeecho_card.dart';
import 'feed_screen.dart';
import 'chat_screen.dart';
import 'messages_screen.dart';
import 'my_letters_screen.dart';
import 'plane_hub_screen.dart';
import 'profile_screen.dart';
import 'salvage_screen.dart';
import 'write_letter_screen.dart';
import 'matching_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> with WidgetsBindingObserver {
  int _index = 0;
  Timer? _notificationTimer;
  final _unread = UnreadController.instance;
  final _notifications = AppNotificationService.instance;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _notifications.tappedPayload.addListener(_handleNotificationTap);
    _notifications.requestPermission();
    _unread.refresh();
    _notificationTimer = Timer.periodic(
      const Duration(seconds: 10),
      (_) => _unread.refresh(),
    );
    WidgetsBinding.instance.addPostFrameCallback(
      (_) => _handleNotificationTap(),
    );
  }

  void _handleNotificationTap() {
    if (!mounted) return;
    final payload = _notifications.consumeTappedPayload();
    if (payload == null) return;
    try {
      final data = jsonDecode(payload);
      if (data is! Map) return;
      if (data['kind'] == 'chat') {
        Navigator.pushNamed(
          context,
          '/chat',
          arguments: ChatScreenArgs(
            roomId: int.tryParse('${data['room_id']}') ?? 0,
            peerName: data['peer_name']?.toString(),
            isTemporary: data['temporary'] == true,
          ),
        ).then((_) => _unread.refresh());
      } else {
        setState(() => _index = 3);
        Future.delayed(const Duration(milliseconds: 250), _unread.refresh);
      }
    } catch (_) {
      setState(() => _index = 3);
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    _notifications.isAppForeground = state == AppLifecycleState.resumed;
    if (state == AppLifecycleState.resumed) _unread.refresh();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _notifications.tappedPayload.removeListener(_handleNotificationTap);
    _notificationTimer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final pages = [
      const HomeTab(),
      const PlaneHubScreen(),
      const FeedScreen(),
      const MessagesScreen(),
      ProfileScreen(onOpenFeed: () => setState(() => _index = 2)),
    ];
    return Scaffold(
      // Keep every tab mounted so an in-progress letter, a salvaged result,
      // scroll position and form input survive bottom navigation switches.
      body: SafeArea(
        child: IndexedStack(index: _index, children: pages),
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        onDestinationSelected: (value) {
          setState(() => _index = value);
          if (value == 3) {
            Future.delayed(const Duration(milliseconds: 300), _unread.refresh);
          }
        },
        destinations: [
          const NavigationDestination(
            icon: Icon(Icons.home_outlined),
            selectedIcon: Icon(Icons.home_rounded),
            label: '首页',
          ),
          const NavigationDestination(
            icon: Icon(Icons.air_outlined),
            selectedIcon: Icon(Icons.air_rounded),
            label: '纸飞机',
          ),
          const NavigationDestination(
            icon: _FeedNavigationIcon(selected: false),
            selectedIcon: _FeedNavigationIcon(selected: true),
            label: '动态',
          ),
          NavigationDestination(
            icon: _UnreadNavigationIcon(selected: false, state: _unread.state),
            selectedIcon: _UnreadNavigationIcon(
              selected: true,
              state: _unread.state,
            ),
            label: '消息',
          ),
          const NavigationDestination(
            icon: Icon(Icons.person_outline_rounded),
            selectedIcon: Icon(Icons.person_rounded),
            label: '我的',
          ),
        ],
      ),
    );
  }
}

class _UnreadNavigationIcon extends StatelessWidget {
  const _UnreadNavigationIcon({required this.selected, required this.state});

  final bool selected;
  final ValueListenable<UnreadState> state;

  @override
  Widget build(BuildContext context) => ValueListenableBuilder<UnreadState>(
        valueListenable: state,
        builder: (context, unread, child) {
          final icon =
              Icon(selected ? Icons.forum_rounded : Icons.forum_outlined);
          if (unread.total <= 0) return icon;
          return Badge(
            label: Text(unread.total > 99 ? '99+' : '${unread.total}'),
            child: icon,
          );
        },
      );
}

class HomeTab extends StatefulWidget {
  const HomeTab({super.key});

  @override
  State<HomeTab> createState() => _HomeTabState();
}

class _HomeTabState extends State<HomeTab> {
  final _userService = UserService();
  final _chatService = ChatService();
  final _matchingService = MatchingService();
  String _name = '晚风';
  MatchingStatus _matching = const MatchingStatus(status: 'IDLE');
  List<ChatRoomInfo> _anonymousRooms = const [];

  @override
  void initState() {
    super.initState();
    _loadName();
    _loadOverview();
  }

  Future<void> _loadOverview() async {
    try {
      final values = await Future.wait([
        _matchingService.status(),
        _chatService.rooms(),
      ]);
      if (!mounted) return;
      setState(() {
        _matching = values[0] as MatchingStatus;
        _anonymousRooms = (values[1] as List<ChatRoomInfo>)
            .where((room) => room.isTemporary)
            .take(5)
            .toList();
      });
    } catch (_) {}
  }

  Future<void> _openMatching() async {
    await Navigator.push(
      context,
      MaterialPageRoute(builder: (_) => const MatchingScreen()),
    );
    if (mounted) _loadOverview();
  }

  Future<void> _openAnonymousRoom(ChatRoomInfo room) async {
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
    if (mounted) _loadOverview();
  }

  Future<void> _loadName() async {
    final localName = await TokenStore().anonymousName;
    if (mounted && localName != null) setState(() => _name = localName);
    try {
      final me = await _userService.me();
      if (mounted) setState(() => _name = me.displayName);
    } catch (_) {
      // 首页在后端离线时仍可正常展示。
    }
  }

  void _open(String title, Widget page) {
    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => Scaffold(
          appBar: AppBar(title: Text(title)),
          body: SafeArea(child: page),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(22),
      children: [
        Text(
          '$_name，晚上好',
          style: Theme.of(
            context,
          ).textTheme.headlineMedium?.copyWith(fontWeight: FontWeight.w900),
        ),
        const SizedBox(height: 16),
        TimeEchoCard(
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  const CircleAvatar(
                    backgroundColor: Color(0xFFE9E1F1),
                    child: Icon(
                      Icons.radar_rounded,
                      color: TimeEchoColors.duskPurple,
                    ),
                  ),
                  const SizedBox(width: 12),
                  const Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          '即时遇见',
                          style: TextStyle(
                            fontSize: 22,
                            fontWeight: FontWeight.w900,
                          ),
                        ),
                        Text('在线匿名聊天'),
                      ],
                    ),
                  ),
                  Chip(
                    label: Text(
                      {'WAITING': '匹配中', 'ACTIVE': '已匹配'}[_matching.status] ??
                          '未匹配',
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 18),
              SizedBox(
                width: double.infinity,
                child: FilledButton.icon(
                  onPressed: _openMatching,
                  icon: Icon(
                    _matching.status == 'ACTIVE'
                        ? Icons.forum_rounded
                        : Icons.waving_hand_rounded,
                  ),
                  label: Text(
                    _matching.status == 'ACTIVE'
                        ? '返回匿名聊天室'
                        : _matching.status == 'WAITING'
                            ? '查看匹配进度'
                            : '开始匹配',
                  ),
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 14),
        TimeEchoCard(
          child: Wrap(
            spacing: 10,
            runSpacing: 10,
            children: [
              _QuickAction(
                icon: Icons.edit_note,
                label: '写一封纸飞机',
                onPressed: () => _open('写纸飞机', const WriteLetterScreen()),
              ),
              _QuickAction(
                icon: Icons.air,
                label: '打捞纸飞机',
                onPressed: () => _open('打捞纸飞机', const SalvageScreen()),
              ),
              _QuickAction(
                icon: Icons.mail_outline,
                label: '我的纸飞机',
                onPressed: () => _open('我的纸飞机', const MyLettersScreen()),
              ),
              ActionChip(
                avatar: const Icon(
                  Icons.auto_graph,
                  color: TimeEchoColors.duskPurple,
                ),
                label: const Text('情绪小结'),
                onPressed: () =>
                    Navigator.pushNamed(context, '/emotion-summary'),
              ),
            ],
          ),
        ),
        const SizedBox(height: 14),
        if (_anonymousRooms.isNotEmpty) ...[
          TimeEchoCard(
            padding: EdgeInsets.zero,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Padding(
                  padding: EdgeInsets.fromLTRB(18, 18, 18, 8),
                  child: Text(
                    '进行中的匿名对话',
                    style: TextStyle(fontSize: 18, fontWeight: FontWeight.w900),
                  ),
                ),
                ..._anonymousRooms.map(
                  (room) => ListTile(
                    onTap: () => _openAnonymousRoom(room),
                    leading: CircleAvatar(
                      backgroundImage: room.peerAvatarUrl == null
                          ? null
                          : NetworkImage(
                              '${AppConfig.apiBaseUrl}${room.peerAvatarUrl}',
                            ),
                      child: room.peerAvatarUrl == null
                          ? const Icon(Icons.person_outline_rounded)
                          : null,
                    ),
                    title: Text(room.peerAnonymousName ?? '匿名回声'),
                    subtitle: Text(room.isMatch ? '即时遇见' : '纸飞机回信'),
                    trailing: room.cardExchangeStatus == 'INVITED'
                        ? const Badge(label: Text('名片'))
                        : const Icon(Icons.chevron_right_rounded),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 14),
        ],
      ],
    );
  }
}

class _FeedNavigationIcon extends StatelessWidget {
  const _FeedNavigationIcon({required this.selected});
  final bool selected;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 42,
      height: 34,
      decoration: BoxDecoration(
        color: selected ? TimeEchoColors.duskPurple : const Color(0xFFE9E1F1),
        borderRadius: BorderRadius.circular(14),
      ),
      child: Icon(
        Icons.bubble_chart_rounded,
        color: selected ? Colors.white : TimeEchoColors.duskPurple,
      ),
    );
  }
}

class _QuickAction extends StatelessWidget {
  const _QuickAction({
    required this.icon,
    required this.label,
    required this.onPressed,
  });

  final IconData icon;
  final String label;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return ActionChip(
      avatar: Icon(icon, size: 18),
      label: Text(label),
      onPressed: onPressed,
    );
  }
}
