import 'dart:async';

import 'package:flutter/material.dart';

import '../core/theme.dart';
import '../services/auth_service.dart';
import '../services/user_service.dart';
import '../widgets/timeecho_card.dart';

class RegisterScreen extends StatefulWidget {
  const RegisterScreen({super.key});

  @override
  State<RegisterScreen> createState() => _RegisterScreenState();
}

class _RegisterScreenState extends State<RegisterScreen> {
  final _formKey = GlobalKey<FormState>();
  final _email = TextEditingController();
  final _username = TextEditingController();
  final _code = TextEditingController();
  final _password = TextEditingController();
  final _confirmPassword = TextEditingController();
  final _auth = AuthService();
  final _userService = UserService();
  Timer? _timer;
  int _countdown = 0;
  int _avatarIndex = 0;
  bool _loading = false;
  bool _obscurePassword = true;
  bool _obscureConfirm = true;
  String? _message;

  static const _avatarAssets = [
    'assets/avatars/avatar-1.png',
    'assets/avatars/avatar-2.png',
    'assets/avatars/avatar-3.png',
    'assets/avatars/avatar-4.png',
    'assets/avatars/avatar-5.png',
    'assets/avatars/avatar-6.png',
  ];

  @override
  void dispose() {
    _timer?.cancel();
    _email.dispose();
    _username.dispose();
    _code.dispose();
    _password.dispose();
    _confirmPassword.dispose();
    super.dispose();
  }

  String? _emailValidator(String? value) {
    if (value == null || value.trim().isEmpty) return '请输入邮箱';
    if (!RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$').hasMatch(value.trim())) {
      return '邮箱格式不正确';
    }
    return null;
  }

  String? _passwordValidator(String? value) {
    if (value == null || value.length < 8 || value.length > 32) {
      return '密码长度应为 8–32 位';
    }
    if (!RegExp(r'[a-z]').hasMatch(value) ||
        !RegExp(r'[A-Z]').hasMatch(value) ||
        !RegExp(r'\d').hasMatch(value)) {
      return '密码需同时包含大写字母、小写字母和数字';
    }
    return null;
  }

  Future<void> _sendCode() async {
    if (_emailValidator(_email.text) != null) {
      setState(() => _message = _emailValidator(_email.text));
      return;
    }
    setState(() {
      _loading = true;
      _message = null;
    });
    try {
      await _auth.sendEmailCode(_email.text);
      if (!mounted) return;
      setState(() {
        _message = '验证码已发送，请检查收件箱和垃圾邮件';
        _countdown = 60;
      });
      _timer?.cancel();
      _timer = Timer.periodic(const Duration(seconds: 1), (timer) {
        if (!mounted || _countdown <= 1) {
          timer.cancel();
          if (mounted) setState(() => _countdown = 0);
        } else {
          setState(() => _countdown--);
        }
      });
    } catch (error) {
      if (mounted) setState(() => _message = error.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _register() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() {
      _loading = true;
      _message = null;
    });
    try {
      await _auth.registerWithEmail(
        email: _email.text,
        password: _password.text,
        code: _code.text,
        username: _username.text,
        avatarUrl: '/static/assets/avatars/avatar-${_avatarIndex + 1}.png',
      );
      try {
        await _userService.updateProfile(
          username: _username.text,
          avatarUrl: '/static/assets/avatars/avatar-${_avatarIndex + 1}.png',
        );
      } catch (_) {
        // Registration itself succeeded. The profile can be retried from "我的".
      }
      if (!mounted) return;
      Navigator.pushNamedAndRemoveUntil(context, '/home', (_) => false);
    } catch (error) {
      if (mounted) setState(() => _message = error.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('创建账号')),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(22, 8, 22, 32),
          children: [
            Text(
              '从一张头像开始',
              style: Theme.of(
                context,
              ).textTheme.headlineMedium?.copyWith(fontWeight: FontWeight.w900),
            ),
            const SizedBox(height: 6),
            const Text(
              '选择一个默认头像，之后仍可以在个人资料中更换。',
              style: TextStyle(color: TimeEchoColors.muted),
            ),
            const SizedBox(height: 18),
            SizedBox(
              height: 70,
              child: ListView.separated(
                scrollDirection: Axis.horizontal,
                itemCount: _avatarAssets.length,
                separatorBuilder: (_, __) => const SizedBox(width: 10),
                itemBuilder: (context, index) {
                  final selected = index == _avatarIndex;
                  return Semantics(
                    label: '默认头像 ${index + 1}',
                    selected: selected,
                    button: true,
                    child: InkWell(
                      borderRadius: BorderRadius.circular(35),
                      onTap: () => setState(() => _avatarIndex = index),
                      child: AnimatedContainer(
                        duration: const Duration(milliseconds: 180),
                        padding: EdgeInsets.all(selected ? 3 : 6),
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
                          radius: 27,
                          backgroundColor: TimeEchoColors.mistBlue,
                          backgroundImage: AssetImage(_avatarAssets[index]),
                        ),
                      ),
                    ),
                  );
                },
              ),
            ),
            const SizedBox(height: 16),
            TimeEchoCard(
              padding: const EdgeInsets.all(20),
              child: Form(
                key: _formKey,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    TextFormField(
                      controller: _email,
                      keyboardType: TextInputType.emailAddress,
                      textInputAction: TextInputAction.next,
                      autofillHints: const [
                        AutofillHints.newUsername,
                        AutofillHints.email,
                      ],
                      decoration: const InputDecoration(
                        labelText: '邮箱',
                        prefixIcon: Icon(Icons.alternate_email_rounded),
                      ),
                      validator: _emailValidator,
                    ),
                    const SizedBox(height: 12),
                    TextFormField(
                      controller: _username,
                      textInputAction: TextInputAction.next,
                      maxLength: 20,
                      decoration: const InputDecoration(
                        labelText: '公开昵称',
                        helperText: '2–20 个字符；纸飞机聊天仍使用匿名代号',
                        prefixIcon: Icon(Icons.badge_outlined),
                      ),
                      validator: (value) {
                        final name = value?.trim() ?? '';
                        final length = name.length;
                        if (length < 2 || length > 20) return '昵称长度应为 2–20 个字符';
                        if (!RegExp(
                          r'^[\u4e00-\u9fa5A-Za-z0-9_]+$',
                        ).hasMatch(name)) {
                          return '昵称仅支持中文、字母、数字或下划线';
                        }
                        return null;
                      },
                    ),
                    const SizedBox(height: 12),
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Expanded(
                          child: TextFormField(
                            controller: _code,
                            keyboardType: TextInputType.number,
                            textInputAction: TextInputAction.next,
                            decoration: const InputDecoration(
                              labelText: '邮箱验证码',
                              prefixIcon: Icon(Icons.verified_outlined),
                            ),
                            validator: (value) =>
                                value == null || value.trim().length < 4
                                    ? '请输入验证码'
                                    : null,
                          ),
                        ),
                        const SizedBox(width: 10),
                        SizedBox(
                          height: 56,
                          child: OutlinedButton(
                            onPressed:
                                _loading || _countdown > 0 ? null : _sendCode,
                            child: Text(
                              _countdown > 0 ? '${_countdown}s' : '发送验证码',
                            ),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 12),
                    TextFormField(
                      controller: _password,
                      obscureText: _obscurePassword,
                      textInputAction: TextInputAction.next,
                      autofillHints: const [AutofillHints.newPassword],
                      decoration: InputDecoration(
                        labelText: '设置密码',
                        helperText: '8–32 位，包含大写字母、小写字母和数字',
                        prefixIcon: const Icon(Icons.lock_outline_rounded),
                        suffixIcon: IconButton(
                          onPressed: () => setState(
                            () => _obscurePassword = !_obscurePassword,
                          ),
                          icon: Icon(
                            _obscurePassword
                                ? Icons.visibility_outlined
                                : Icons.visibility_off_outlined,
                          ),
                        ),
                      ),
                      validator: _passwordValidator,
                    ),
                    const SizedBox(height: 12),
                    TextFormField(
                      controller: _confirmPassword,
                      obscureText: _obscureConfirm,
                      textInputAction: TextInputAction.next,
                      autofillHints: const [AutofillHints.newPassword],
                      decoration: InputDecoration(
                        labelText: '确认密码',
                        prefixIcon: const Icon(Icons.lock_reset_rounded),
                        suffixIcon: IconButton(
                          onPressed: () => setState(
                            () => _obscureConfirm = !_obscureConfirm,
                          ),
                          icon: Icon(
                            _obscureConfirm
                                ? Icons.visibility_outlined
                                : Icons.visibility_off_outlined,
                          ),
                        ),
                      ),
                      validator: (value) =>
                          value != _password.text ? '两次输入的密码不一致' : null,
                    ),
                    const SizedBox(height: 18),
                    FilledButton(
                      onPressed: _loading ? null : _register,
                      child: _loading
                          ? const SizedBox(
                              width: 22,
                              height: 22,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Text('注册并登录'),
                    ),
                    if (_message != null) ...[
                      const SizedBox(height: 14),
                      Text(_message!, textAlign: TextAlign.center),
                    ],
                  ],
                ),
              ),
            ),
            const Padding(
              padding: EdgeInsets.symmetric(horizontal: 10, vertical: 10),
              child: Text(
                '注册即表示你同意社区规则。请勿在公开内容或匿名聊天中透露密码、验证码等敏感信息。',
                style: TextStyle(
                  fontSize: 12,
                  color: TimeEchoColors.muted,
                  height: 1.5,
                ),
                textAlign: TextAlign.center,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
