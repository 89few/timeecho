import 'package:flutter/material.dart';

import '../core/app_notification_service.dart';
import '../services/auth_service.dart';
import '../widgets/timeecho_card.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  final _notificationService = AppNotificationService.instance;
  NotificationPreferences? _notificationPreferences;
  String? _message;

  @override
  void initState() {
    super.initState();
    _loadNotificationPreferences();
  }

  Future<void> _loadNotificationPreferences() async {
    final value = await _notificationService.preferences();
    if (mounted) setState(() => _notificationPreferences = value);
  }

  Future<void> _updateNotifications(NotificationPreferences value) async {
    setState(() => _notificationPreferences = value);
    await _notificationService.savePreferences(value);
    if (value.enabled) {
      final granted = await _notificationService.requestPermission();
      if (mounted && !granted) {
        setState(() => _message = '系统通知权限未开启，请在 Android 设置中允许通知');
      }
    }
  }

  Future<void> _logout() async {
    await AuthService().logout();
    if (!mounted) return;
    Navigator.pushNamedAndRemoveUntil(context, '/login', (_) => false);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('设置')),
      body: ListView(
        padding: const EdgeInsets.all(22),
        children: [
          TimeEchoCard(
            padding: EdgeInsets.zero,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Padding(
                  padding: EdgeInsets.fromLTRB(18, 18, 18, 6),
                  child: Text(
                    '通知',
                    style: TextStyle(fontSize: 17, fontWeight: FontWeight.w900),
                  ),
                ),
                SwitchListTile(
                  secondary: const Icon(Icons.notifications_active_outlined),
                  title: const Text('新消息通知'),
                  value: _notificationPreferences?.enabled ?? true,
                  onChanged: _notificationPreferences == null
                      ? null
                      : (value) => _updateNotifications(
                            _notificationPreferences!.copyWith(enabled: value),
                          ),
                ),
                SwitchListTile(
                  secondary: const Icon(Icons.visibility_outlined),
                  title: const Text('消息预览'),
                  value: _notificationPreferences?.preview ?? true,
                  onChanged: _notificationPreferences?.enabled != true
                      ? null
                      : (value) => _updateNotifications(
                            _notificationPreferences!.copyWith(preview: value),
                          ),
                ),
                SwitchListTile(
                  secondary: const Icon(Icons.volume_up_outlined),
                  title: const Text('通知声音'),
                  value: _notificationPreferences?.sound ?? true,
                  onChanged: _notificationPreferences?.enabled != true
                      ? null
                      : (value) => _updateNotifications(
                            _notificationPreferences!.copyWith(sound: value),
                          ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 18),
          OutlinedButton(onPressed: _logout, child: const Text('退出登录')),
          if (_message != null)
            Padding(
              padding: const EdgeInsets.only(top: 14),
              child: Text(_message!),
            ),
        ],
      ),
    );
  }
}
