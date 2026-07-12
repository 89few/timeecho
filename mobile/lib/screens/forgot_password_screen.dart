import 'package:flutter/material.dart';

import '../core/theme.dart';
import '../services/auth_service.dart';
import '../widgets/timeecho_card.dart';

class ForgotPasswordScreen extends StatefulWidget {
  const ForgotPasswordScreen({super.key});

  @override
  State<ForgotPasswordScreen> createState() => _ForgotPasswordScreenState();
}

class _ForgotPasswordScreenState extends State<ForgotPasswordScreen> {
  final _email = TextEditingController();
  final _code = TextEditingController();
  final _password = TextEditingController();
  final _confirm = TextEditingController();
  final _auth = AuthService();
  bool _codeRequested = false;
  bool _loading = false;
  bool _obscure = true;
  String? _message;

  @override
  void dispose() {
    _email.dispose();
    _code.dispose();
    _password.dispose();
    _confirm.dispose();
    super.dispose();
  }

  bool get _validEmail =>
      RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$').hasMatch(_email.text.trim());

  Future<void> _requestCode() async {
    if (!_validEmail) {
      setState(() => _message = '请输入正确的邮箱地址');
      return;
    }
    setState(() {
      _loading = true;
      _message = null;
    });
    try {
      await _auth.requestPasswordReset(_email.text);
      if (mounted) {
        setState(() {
          _codeRequested = true;
          _message = '如果该邮箱已注册，重置验证码会发送到它的收件箱';
        });
      }
    } catch (error) {
      if (mounted) setState(() => _message = error.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _reset() async {
    if (_code.text.trim().length < 4) {
      setState(() => _message = '请输入邮件中的验证码');
      return;
    }
    final password = _password.text;
    if (password.length < 8 ||
        password.length > 32 ||
        !RegExp(r'[a-z]').hasMatch(password) ||
        !RegExp(r'[A-Z]').hasMatch(password) ||
        !RegExp(r'\d').hasMatch(password)) {
      setState(() => _message = '新密码需为 8–32 位，并包含大小写字母和数字');
      return;
    }
    if (_confirm.text != password) {
      setState(() => _message = '两次输入的密码不一致');
      return;
    }
    setState(() {
      _loading = true;
      _message = null;
    });
    try {
      await _auth.resetPassword(
        email: _email.text,
        code: _code.text,
        newPassword: password,
      );
      if (!mounted) return;
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('密码已重置，请使用新密码登录')));
      Navigator.pop(context);
    } catch (error) {
      if (mounted) setState(() => _message = error.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('找回密码')),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(22, 10, 22, 32),
          children: [
            Icon(
              Icons.mark_email_read_outlined,
              size: 58,
              color: Theme.of(context).colorScheme.primary,
            ),
            const SizedBox(height: 16),
            Text(
              '用注册邮箱验证身份',
              textAlign: TextAlign.center,
              style: Theme.of(
                context,
              ).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w900),
            ),
            const SizedBox(height: 8),
            const Text(
              '验证码只用于本次密码重置，请勿转发给任何人。',
              textAlign: TextAlign.center,
              style: TextStyle(color: TimeEchoColors.muted),
            ),
            const SizedBox(height: 24),
            TimeEchoCard(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  TextField(
                    controller: _email,
                    readOnly: _codeRequested,
                    keyboardType: TextInputType.emailAddress,
                    decoration: const InputDecoration(
                      labelText: '注册邮箱',
                      prefixIcon: Icon(Icons.alternate_email_rounded),
                    ),
                  ),
                  if (_codeRequested) ...[
                    const SizedBox(height: 12),
                    TextField(
                      controller: _code,
                      keyboardType: TextInputType.number,
                      decoration: const InputDecoration(
                        labelText: '重置验证码',
                        prefixIcon: Icon(Icons.verified_outlined),
                      ),
                    ),
                    const SizedBox(height: 12),
                    TextField(
                      controller: _password,
                      obscureText: _obscure,
                      decoration: InputDecoration(
                        labelText: '新密码',
                        helperText: '8–32 位，包含大小写字母和数字',
                        prefixIcon: const Icon(Icons.lock_outline_rounded),
                        suffixIcon: IconButton(
                          onPressed: () => setState(() => _obscure = !_obscure),
                          icon: Icon(
                            _obscure
                                ? Icons.visibility_outlined
                                : Icons.visibility_off_outlined,
                          ),
                        ),
                      ),
                    ),
                    const SizedBox(height: 12),
                    TextField(
                      controller: _confirm,
                      obscureText: _obscure,
                      decoration: const InputDecoration(
                        labelText: '再次输入新密码',
                        prefixIcon: Icon(Icons.lock_reset_rounded),
                      ),
                    ),
                  ],
                  const SizedBox(height: 18),
                  FilledButton(
                    onPressed: _loading
                        ? null
                        : (_codeRequested ? _reset : _requestCode),
                    child: _loading
                        ? const SizedBox(
                            width: 22,
                            height: 22,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : Text(_codeRequested ? '确认重置密码' : '发送重置验证码'),
                  ),
                  if (_codeRequested)
                    TextButton(
                      onPressed: _loading ? null : _requestCode,
                      child: const Text('没有收到？重新发送'),
                    ),
                  if (_message != null) ...[
                    const SizedBox(height: 10),
                    Text(_message!, textAlign: TextAlign.center),
                  ],
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
