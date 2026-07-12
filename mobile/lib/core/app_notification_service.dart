import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../models/chat_room.dart';
import '../models/social.dart';

class NotificationPreferences {
  const NotificationPreferences({
    required this.enabled,
    required this.preview,
    required this.sound,
  });

  final bool enabled;
  final bool preview;
  final bool sound;

  NotificationPreferences copyWith({
    bool? enabled,
    bool? preview,
    bool? sound,
  }) =>
      NotificationPreferences(
        enabled: enabled ?? this.enabled,
        preview: preview ?? this.preview,
        sound: sound ?? this.sound,
      );
}

/// Owns Android/iOS local notification channels and user preferences.
/// Remote delivery after the process is killed still requires FCM or a vendor
/// push service; while TimeEcho is alive, unread polling feeds this service.
class AppNotificationService {
  AppNotificationService._();

  static final AppNotificationService instance = AppNotificationService._();

  static const _enabledKey = 'timeecho_notifications_enabled';
  static const _previewKey = 'timeecho_notification_preview';
  static const _soundKey = 'timeecho_notification_sound';

  final FlutterLocalNotificationsPlugin _plugin =
      FlutterLocalNotificationsPlugin();
  final ValueNotifier<String?> tappedPayload = ValueNotifier<String?>(null);

  bool _initialized = false;
  bool isAppForeground = true;
  int? activeRoomId;

  Future<void> initialize() async {
    if (_initialized || kIsWeb) return;
    try {
      const android = AndroidInitializationSettings('ic_stat_timeecho');
      const settings = InitializationSettings(android: android);
      await _plugin.initialize(
        settings: settings,
        onDidReceiveNotificationResponse: (response) {
          if (response.payload?.isNotEmpty == true) {
            tappedPayload.value = response.payload;
          }
        },
      );
      final launch = await _plugin.getNotificationAppLaunchDetails();
      final payload = launch?.notificationResponse?.payload;
      if (launch?.didNotificationLaunchApp == true &&
          payload?.isNotEmpty == true) {
        tappedPayload.value = payload;
      }
      _initialized = true;
    } catch (error) {
      // Widget tests and unsupported platforms do not register this plugin.
      debugPrint('notification initialization failed: $error');
    }
  }

  Future<bool> requestPermission() async {
    await initialize();
    try {
      return await _plugin
              .resolvePlatformSpecificImplementation<
                  AndroidFlutterLocalNotificationsPlugin>()
              ?.requestNotificationsPermission() ??
          true;
    } catch (_) {
      return false;
    }
  }

  Future<NotificationPreferences> preferences() async {
    final prefs = await SharedPreferences.getInstance();
    return NotificationPreferences(
      enabled: prefs.getBool(_enabledKey) ?? true,
      preview: prefs.getBool(_previewKey) ?? true,
      sound: prefs.getBool(_soundKey) ?? true,
    );
  }

  Future<void> savePreferences(NotificationPreferences value) async {
    final prefs = await SharedPreferences.getInstance();
    await Future.wait([
      prefs.setBool(_enabledKey, value.enabled),
      prefs.setBool(_previewKey, value.preview),
      prefs.setBool(_soundKey, value.sound),
    ]);
    if (!value.enabled) {
      try {
        await _plugin.cancelAll();
      } catch (_) {}
    }
  }

  Future<void> showChat(ChatRoomInfo room) async {
    // Suppress a banner only while the user is visibly reading this room.
    // Keeping the same route on the navigation stack must not silence
    // notifications after the app is sent to the background.
    if ((isAppForeground && room.roomId == activeRoomId) ||
        room.unreadCount <= 0) {
      return;
    }
    final prefs = await preferences();
    if (!prefs.enabled) return;
    await _show(
      id: 100000 + room.roomId,
      title: room.peerAnonymousName ?? (room.isTemporary ? '匿名回声' : '好友消息'),
      body: prefs.preview ? (room.lastMessage ?? '你收到一条新消息') : '你收到一条新消息',
      channelId: 'timeecho_messages',
      channelName: '聊天消息',
      channelDescription: '好友私信和纸飞机临时回信',
      sound: prefs.sound,
      payload: jsonEncode({
        'kind': 'chat',
        'room_id': room.roomId,
        'peer_name': room.peerAnonymousName,
        'temporary': room.isTemporary,
      }),
    );
  }

  /// Delivers a banner for a message that arrived on an already connected
  /// room while Android has put the application in the background. The
  /// server correctly considers the socket delivery successful, so this path
  /// cannot depend on the unread counter being incremented later.
  Future<void> showConnectedChatMessage({
    required int roomId,
    required String title,
    required String body,
    required bool temporary,
  }) async {
    if (isAppForeground) return;
    final prefs = await preferences();
    if (!prefs.enabled) return;
    await _show(
      id: 100000 + roomId,
      title: title,
      body: prefs.preview ? body : '你收到一条新消息',
      channelId: 'timeecho_messages',
      channelName: '聊天消息',
      channelDescription: '好友私信和纸飞机临时回信',
      sound: prefs.sound,
      payload: jsonEncode({
        'kind': 'chat',
        'room_id': roomId,
        'peer_name': title,
        'temporary': temporary,
      }),
    );
  }

  Future<void> showSocial(SocialNotification notification) async {
    final prefs = await preferences();
    if (!prefs.enabled) return;
    await _show(
      id: 200000 + notification.id,
      title: notification.title,
      body: prefs.preview ? notification.message : '你收到一条新通知',
      channelId: 'timeecho_social',
      channelName: '互动通知',
      channelDescription: '好友申请、点赞和评论',
      sound: prefs.sound,
      payload: jsonEncode({
        'kind': 'social',
        'notification_id': notification.id,
      }),
    );
  }

  Future<void> showTestNotification() async {
    final prefs = await preferences();
    if (!prefs.enabled) return;
    await _show(
      id: 299999,
      title: 'TimeEcho 通知已开启',
      body: prefs.preview ? '新消息会在这里提醒你' : '你收到一条新消息',
      channelId: 'timeecho_social',
      channelName: '互动通知',
      channelDescription: '好友申请、点赞和评论',
      sound: prefs.sound,
      payload: jsonEncode({'kind': 'social', 'notification_id': 0}),
    );
  }

  Future<void> _show({
    required int id,
    required String title,
    required String body,
    required String channelId,
    required String channelName,
    required String channelDescription,
    required bool sound,
    required String payload,
  }) async {
    await initialize();
    if (!_initialized) return;
    try {
      final details = NotificationDetails(
        android: AndroidNotificationDetails(
          channelId,
          channelName,
          channelDescription: channelDescription,
          icon: 'ic_stat_timeecho',
          importance: Importance.high,
          priority: Priority.high,
          playSound: sound,
          enableVibration: true,
          category: AndroidNotificationCategory.message,
          visibility: NotificationVisibility.private,
          number: 1,
        ),
      );
      await _plugin.show(
        id: id,
        title: title,
        body: body,
        notificationDetails: details,
        payload: payload,
      );
    } catch (error) {
      // Notification failure must never break chat or social refresh.
      debugPrint('notification delivery failed: $error');
    }
  }

  String? consumeTappedPayload() {
    final value = tappedPayload.value;
    tappedPayload.value = null;
    return value;
  }
}
