import 'package:flutter/material.dart';

import '../services/auth_service.dart';

class ChangePasswordScreen extends StatefulWidget {
  const ChangePasswordScreen({super.key, required this.currentPassword});
  final String currentPassword;

  @override
  State<ChangePasswordScreen> createState() => _ChangePasswordScreenState();
}

class _ChangePasswordScreenState extends State<ChangePasswordScreen> {
  final _password = TextEditingController();
  final _confirm = TextEditingController();
  bool _loading = false;
  String? _error;

  @override
  void dispose() {
    _password.dispose();
    _confirm.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final password = _password.text;
    if (password.length < 8 || !RegExp(r'[A-Za-z]').hasMatch(password) || !RegExp(r'\d').hasMatch(password)) {
      setState(() => _error = '新密码至少 8 位，并包含字母和数字');
      return;
    }
    if (password != _confirm.text) {
      setState(() => _error = '两次输入的密码不一致');
      return;
    }
    setState(() { _loading = true; _error = null; });
    try {
      await AuthService().changePassword(currentPassword: widget.currentPassword, newPassword: password);
      if (mounted) Navigator.pushNamedAndRemoveUntil(context, '/login', (_) => false);
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('设置新密码'), automaticallyImplyLeading: false),
    body: ListView(
      padding: const EdgeInsets.all(24),
      children: [
        const Text('这是管理员创建的临时密码，首次登录必须修改。'),
        const SizedBox(height: 20),
        TextField(controller: _password, obscureText: true, decoration: const InputDecoration(labelText: '新密码')),
        const SizedBox(height: 12),
        TextField(controller: _confirm, obscureText: true, decoration: const InputDecoration(labelText: '确认新密码')),
        if (_error != null) Padding(padding: const EdgeInsets.only(top: 12), child: Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error))),
        const SizedBox(height: 20),
        FilledButton(onPressed: _loading ? null : _submit, child: Text(_loading ? '提交中…' : '修改并重新登录')),
      ],
    ),
  );
}
