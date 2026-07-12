import 'dart:io';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import '../core/theme.dart';
import '../models/user.dart';
import '../services/auth_service.dart';
import '../services/user_service.dart';
import '../widgets/social_avatar.dart';
import '../widgets/timeecho_card.dart';
import 'emotion_summary_screen.dart';
import 'friends_screen.dart';
import 'settings_screen.dart';

class ProfileScreen extends StatefulWidget {
  const ProfileScreen({super.key, this.onOpenFeed});

  final VoidCallback? onOpenFeed;

  @override
  State<ProfileScreen> createState() => _ProfileScreenState();
}

class _ProfileScreenState extends State<ProfileScreen> {
  final _service = UserService();
  UserProfile? _profile;
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load({bool forceRefresh = false}) async {
    setState(() {
      if (_profile == null) _loading = true;
      _error = null;
    });
    try {
      final value = await _service.me(forceRefresh: forceRefresh);
      if (mounted) setState(() => _profile = value);
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _editProfile() async {
    final profile = _profile;
    if (profile == null) return;
    final updated = await showModalBottomSheet<UserProfile>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      backgroundColor: TimeEchoColors.surface,
      builder: (_) => _EditProfileSheet(profile: profile, service: _service),
    );
    if (updated != null && mounted) setState(() => _profile = updated);
  }

  Future<void> _logout() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('退出登录？'),
        content: const Text('退出后，本机保存的登录凭证会被清除。'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('取消'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('退出'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    await AuthService().logout();
    if (mounted) {
      Navigator.pushNamedAndRemoveUntil(context, '/login', (_) => false);
    }
  }

  void _push(Widget child) =>
      Navigator.push(context, MaterialPageRoute(builder: (_) => child));

  @override
  Widget build(BuildContext context) {
    return RefreshIndicator(
      onRefresh: () => _load(forceRefresh: true),
      child: ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.fromLTRB(18, 18, 18, 110),
        children: [
          Row(
            children: [
              Text(
                '我的',
                style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                      fontWeight: FontWeight.w900,
                    ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          if (_loading && _profile == null)
            const Padding(
              padding: EdgeInsets.all(44),
              child: Center(child: CircularProgressIndicator()),
            )
          else if (_error != null)
            TimeEchoCard(
              child: Column(
                children: [
                  const Icon(
                    Icons.cloud_off_rounded,
                    size: 42,
                    color: TimeEchoColors.duskPurple,
                  ),
                  const SizedBox(height: 10),
                  Text(_error!, textAlign: TextAlign.center),
                  const SizedBox(height: 12),
                  FilledButton.tonal(onPressed: _load, child: const Text('重试')),
                ],
              ),
            )
          else if (_profile != null) ...[
            _ProfileHeader(profile: _profile!, onEdit: _editProfile),
            const SizedBox(height: 14),
            Row(
              children: [
                Expanded(
                  child: _StatCard(
                    value: '${_profile!.friendCount}',
                    label: '好友',
                    onTap: () => Navigator.push(
                      context,
                      MaterialPageRoute(builder: (_) => const FriendsScreen()),
                    ),
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: _StatCard(
                    value: '${_profile!.postCount}',
                    label: '动态',
                    onTap: widget.onOpenFeed ?? () {},
                  ),
                ),
              ],
            ),
          ],
          const SizedBox(height: 14),
          TimeEchoCard(
            padding: EdgeInsets.zero,
            child: Column(
              children: [
                _MenuTile(
                  icon: Icons.people_alt_outlined,
                  color: const Color(0xFF708CAB),
                  title: '好友',
                  onTap: () => Navigator.push(
                    context,
                    MaterialPageRoute(builder: (_) => const FriendsScreen()),
                  ),
                ),
                const Divider(height: 1, indent: 66),
                _MenuTile(
                  icon: Icons.auto_graph_rounded,
                  color: TimeEchoColors.mossGreen,
                  title: '情绪小结',
                  onTap: () => _push(const EmotionSummaryScreen()),
                ),
                const Divider(height: 1, indent: 66),
                _MenuTile(
                  icon: Icons.settings_outlined,
                  color: TimeEchoColors.duskPurple,
                  title: '设置',
                  onTap: () => _push(const SettingsScreen()),
                ),
              ],
            ),
          ),
          const SizedBox(height: 14),
          OutlinedButton.icon(
            onPressed: _logout,
            icon: const Icon(Icons.logout_rounded),
            label: const Text('退出登录'),
            style: OutlinedButton.styleFrom(
              foregroundColor: Theme.of(context).colorScheme.error,
              padding: const EdgeInsets.symmetric(vertical: 14),
            ),
          ),
        ],
      ),
    );
  }
}

class _ProfileHeader extends StatelessWidget {
  const _ProfileHeader({required this.profile, required this.onEdit});
  final UserProfile profile;
  final VoidCallback onEdit;

  @override
  Widget build(BuildContext context) {
    return TimeEchoCard(
      padding: const EdgeInsets.all(20),
      child: Row(
        children: [
          SocialAvatar(
            name: profile.displayName,
            url: profile.avatarUrl,
            radius: 38,
          ),
          const SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  profile.displayName,
                  style: const TextStyle(
                    fontSize: 21,
                    fontWeight: FontWeight.w900,
                  ),
                ),
                const SizedBox(height: 3),
                if (profile.uid != null)
                  Text(
                    'UID ${profile.uid}',
                    style: const TextStyle(
                      color: TimeEchoColors.muted,
                      fontSize: 13,
                    ),
                  ),
                if (profile.email != null)
                  Text(
                    profile.email!,
                    style: const TextStyle(color: TimeEchoColors.muted),
                  ),
                const SizedBox(height: 7),
                Text(
                  profile.bio?.trim().isNotEmpty == true
                      ? profile.bio!
                      : '还没有写个人简介',
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                ),
              ],
            ),
          ),
          IconButton.filledTonal(
            onPressed: onEdit,
            tooltip: '编辑资料',
            icon: const Icon(Icons.edit_outlined),
          ),
        ],
      ),
    );
  }
}

class _StatCard extends StatelessWidget {
  const _StatCard({
    required this.value,
    required this.label,
    required this.onTap,
  });
  final String value;
  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(18),
        child: Ink(
          padding: const EdgeInsets.symmetric(vertical: 14, horizontal: 6),
          decoration: BoxDecoration(
            color: TimeEchoColors.surface,
            borderRadius: BorderRadius.circular(18),
          ),
          child: Column(
            children: [
              Text(
                value,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style:
                    const TextStyle(fontSize: 17, fontWeight: FontWeight.w900),
              ),
              const SizedBox(height: 3),
              Text(
                label,
                style:
                    const TextStyle(fontSize: 12, color: TimeEchoColors.muted),
              ),
            ],
          ),
        ),
      );
}

class _MenuTile extends StatelessWidget {
  const _MenuTile({
    required this.icon,
    required this.color,
    required this.title,
    required this.onTap,
  });
  final IconData icon;
  final Color color;
  final String title;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => ListTile(
        onTap: onTap,
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
        leading: Container(
          width: 40,
          height: 40,
          decoration: BoxDecoration(
            color: color.withValues(alpha: .12),
            borderRadius: BorderRadius.circular(13),
          ),
          child: Icon(icon, color: color),
        ),
        title: Text(title, style: const TextStyle(fontWeight: FontWeight.w800)),
        trailing: const Icon(Icons.chevron_right_rounded),
      );
}

class _EditProfileSheet extends StatefulWidget {
  const _EditProfileSheet({required this.profile, required this.service});
  final UserProfile profile;
  final UserService service;

  @override
  State<_EditProfileSheet> createState() => _EditProfileSheetState();
}

class _EditProfileSheetState extends State<_EditProfileSheet> {
  late final TextEditingController _username;
  late final TextEditingController _bio;
  late String _avatarUrl;
  String? _customAvatarPath;
  final _picker = ImagePicker();
  bool _saving = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _username = TextEditingController(text: widget.profile.username ?? '');
    _bio = TextEditingController(text: widget.profile.bio ?? '');
    _avatarUrl =
        widget.profile.avatarUrl ?? '/static/assets/avatars/avatar-1.png';
  }

  @override
  void dispose() {
    _username.dispose();
    _bio.dispose();
    super.dispose();
  }

  Future<void> _pickAvatar(ImageSource source) async {
    final file = await _picker.pickImage(
      source: source,
      imageQuality: 86,
      maxWidth: 1200,
      maxHeight: 1200,
    );
    if (file != null && mounted) {
      setState(() => _customAvatarPath = file.path);
    }
  }

  Future<void> _save() async {
    final name = _username.text.trim();
    if (name.length < 2 ||
        name.length > 20 ||
        !RegExp(r'^[\u4e00-\u9fa5A-Za-z0-9_]+$').hasMatch(name)) {
      setState(() => _error = '昵称需为 2–20 位中文、字母、数字或下划线');
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      if (_customAvatarPath != null) {
        final uploaded = await widget.service.uploadAvatar(_customAvatarPath!);
        _avatarUrl = uploaded.avatarUrl ?? _avatarUrl;
      }
      final profile = await widget.service.updateProfile(
        username: name,
        bio: _bio.text,
        avatarUrl: _avatarUrl,
      );
      if (mounted) Navigator.pop(context, profile);
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.fromLTRB(
        20,
        10,
        20,
        20 + MediaQuery.viewInsetsOf(context).bottom,
      ),
      child: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Center(
              child: Container(
                width: 42,
                height: 4,
                decoration: BoxDecoration(
                  color: Colors.black12,
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
            ),
            const SizedBox(height: 18),
            const Text(
              '编辑个人资料',
              style: TextStyle(fontSize: 21, fontWeight: FontWeight.w900),
            ),
            const SizedBox(height: 16),
            Center(
              child: Stack(
                clipBehavior: Clip.none,
                children: [
                  CircleAvatar(
                    radius: 43,
                    backgroundImage: _customAvatarPath != null
                        ? FileImage(File(_customAvatarPath!))
                        : null,
                    child: _customAvatarPath == null
                        ? SocialAvatar(
                            name: widget.profile.displayName,
                            url: _avatarUrl,
                            radius: 43,
                          )
                        : null,
                  ),
                  Positioned(
                    right: -4,
                    bottom: -4,
                    child: IconButton.filled(
                      tooltip: '从相册选择头像',
                      onPressed: _saving
                          ? null
                          : () => _pickAvatar(ImageSource.gallery),
                      icon: const Icon(Icons.photo_camera_outlined),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed:
                        _saving ? null : () => _pickAvatar(ImageSource.gallery),
                    icon: const Icon(Icons.photo_library_outlined),
                    label: const Text('选择本地照片'),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed:
                        _saving ? null : () => _pickAvatar(ImageSource.camera),
                    icon: const Icon(Icons.camera_alt_outlined),
                    label: const Text('拍照'),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            const Text(
              '或者使用系统头像',
              style: TextStyle(color: TimeEchoColors.muted),
            ),
            const SizedBox(height: 8),
            SizedBox(
              height: 62,
              child: ListView.separated(
                scrollDirection: Axis.horizontal,
                itemCount: 6,
                separatorBuilder: (_, __) => const SizedBox(width: 9),
                itemBuilder: (context, index) {
                  final url = '/static/assets/avatars/avatar-${index + 1}.png';
                  final selected = _avatarUrl.endsWith(
                    'avatar-${index + 1}.png',
                  );
                  return GestureDetector(
                    onTap: () => setState(() {
                      _avatarUrl = url;
                      _customAvatarPath = null;
                    }),
                    child: AnimatedContainer(
                      duration: const Duration(milliseconds: 160),
                      padding: const EdgeInsets.all(3),
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        border: Border.all(
                          color: selected
                              ? TimeEchoColors.duskPurple
                              : Colors.transparent,
                          width: 2,
                        ),
                      ),
                      child: CircleAvatar(
                        radius: 25,
                        backgroundImage: AssetImage(
                          'assets/avatars/avatar-${index + 1}.png',
                        ),
                      ),
                    ),
                  );
                },
              ),
            ),
            const SizedBox(height: 14),
            TextField(
              controller: _username,
              maxLength: 20,
              decoration: const InputDecoration(
                labelText: '公开昵称',
                prefixIcon: Icon(Icons.badge_outlined),
              ),
            ),
            const SizedBox(height: 10),
            TextField(
              controller: _bio,
              maxLength: 120,
              minLines: 2,
              maxLines: 3,
              decoration: const InputDecoration(
                labelText: '个人简介',
                prefixIcon: Icon(Icons.notes_rounded),
              ),
            ),
            if (_error != null)
              Padding(
                padding: const EdgeInsets.only(top: 10),
                child: Text(
                  _error!,
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
                ),
              ),
            const SizedBox(height: 16),
            FilledButton(
              onPressed: _saving ? null : _save,
              child: _saving
                  ? const SizedBox(
                      width: 22,
                      height: 22,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Text('保存资料'),
            ),
          ],
        ),
      ),
    );
  }
}
