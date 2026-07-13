import 'package:flutter/material.dart';

import '../core/app_config.dart';
import '../core/theme.dart';
import '../services/auth_service.dart';
import '../widgets/timeecho_card.dart';
import 'forgot_password_screen.dart';
import 'register_screen.dart';
import 'change_password_screen.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  static const _enableDevPhoneLogin = bool.fromEnvironment(
    'ENABLE_DEV_PHONE_LOGIN',
    defaultValue: false,
  );
  final _formKey = GlobalKey<FormState>();
  final _identifier = TextEditingController();
  final _password = TextEditingController();
  final _phone = TextEditingController(text: '13800000001');
  final _code = TextEditingController(text: '123456');
  final _auth = AuthService();
  bool _loading = false;
  bool _obscurePassword = true;
  String? _message;

  @override
  void dispose() {
    _identifier.dispose();
    _password.dispose();
    _phone.dispose();
    _code.dispose();
    super.dispose();
  }

  Future<void> _login() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() {
      _loading = true;
      _message = null;
    });
    try {
      await _auth.loginWithPassword(
        identifier: _identifier.text,
        password: _password.text,
      );
      if (!mounted) return;
      if (_auth.lastLoginRequiresPasswordChange) {
        await Navigator.pushReplacement(
          context,
          MaterialPageRoute(
            builder: (_) => ChangePasswordScreen(
              currentPassword: _password.text,
            ),
          ),
        );
        return;
      }
      Navigator.pushNamedAndRemoveUntil(context, '/home', (_) => false);
    } catch (error) {
      if (mounted) setState(() => _message = error.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _developmentLogin() async {
    setState(() {
      _loading = true;
      _message = null;
    });
    try {
      await _auth.sendCode(_phone.text.trim());
      await _auth.login(phone: _phone.text.trim(), code: _code.text.trim());
      if (!mounted) return;
      Navigator.pushNamedAndRemoveUntil(context, '/home', (_) => false);
    } catch (error) {
      if (mounted) setState(() => _message = error.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _editBackendAddress() async {
    final controller = TextEditingController(text: AppConfig.apiBaseUrl);
    final value = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('服务器地址'),
        content: TextField(
          controller: controller,
          keyboardType: TextInputType.url,
          autocorrect: false,
          decoration: const InputDecoration(
            labelText: 'HTTPS 地址',
            hintText: 'https://api.example.com',
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('取消'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, controller.text),
            child: const Text('保存'),
          ),
        ],
      ),
    );
    controller.dispose();
    if (value != null && value.trim().isNotEmpty) {
      await AppConfig.setApiBaseUrl(value);
      if (mounted) setState(() => _message = '服务器地址已更新');
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Stack(
          children: [
            Positioned(
              right: -70,
              top: -80,
              child: Container(
                width: 230,
                height: 230,
                decoration: const BoxDecoration(
                  color: TimeEchoColors.mistBlue,
                  shape: BoxShape.circle,
                ),
              ),
            ),
            ListView(
              padding: const EdgeInsets.fromLTRB(24, 24, 24, 32),
              children: [
                if (AppConfig.allowBackendOverride) ...[
                  Align(
                    alignment: Alignment.centerRight,
                    child: IconButton.filledTonal(
                      tooltip: '服务器设置',
                      onPressed: _editBackendAddress,
                      icon: const Icon(Icons.dns_outlined),
                    ),
                  ),
                  const SizedBox(height: 20),
                ] else
                  const SizedBox(height: 48),
                const _BrandHeader(
                  title: '欢迎回来',
                  subtitle: '',
                ),
                const SizedBox(height: 28),
                TimeEchoCard(
                  padding: const EdgeInsets.all(20),
                  child: Form(
                    key: _formKey,
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        TextFormField(
                          controller: _identifier,
                          keyboardType: TextInputType.emailAddress,
                          textInputAction: TextInputAction.next,
                          autofillHints: const [
                            AutofillHints.email,
                            AutofillHints.username,
                          ],
                          decoration: const InputDecoration(
                            labelText: '邮箱账号',
                            prefixIcon: Icon(Icons.alternate_email_rounded),
                          ),
                          validator: (value) {
                            if (value == null || value.trim().isEmpty) {
                              return '请输入邮箱';
                            }
                            if (!RegExp(
                              r'^[^@\s]+@[^@\s]+\.[^@\s]+$',
                            ).hasMatch(value.trim())) {
                              return '邮箱格式不正确';
                            }
                            return null;
                          },
                        ),
                        const SizedBox(height: 14),
                        TextFormField(
                          controller: _password,
                          obscureText: _obscurePassword,
                          textInputAction: TextInputAction.done,
                          autofillHints: const [AutofillHints.password],
                          onFieldSubmitted: (_) => _loading ? null : _login(),
                          decoration: InputDecoration(
                            labelText: '密码',
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
                          validator: (value) =>
                              value == null || value.isEmpty ? '请输入密码' : null,
                        ),
                        Align(
                          alignment: Alignment.centerRight,
                          child: TextButton(
                            onPressed: _loading
                                ? null
                                : () => Navigator.push(
                                      context,
                                      MaterialPageRoute(
                                        builder: (_) =>
                                            const ForgotPasswordScreen(),
                                      ),
                                    ),
                            child: const Text('忘记密码？'),
                          ),
                        ),
                        FilledButton(
                          onPressed: _loading ? null : _login,
                          child: _loading
                              ? const SizedBox(
                                  width: 22,
                                  height: 22,
                                  child: CircularProgressIndicator(
                                    strokeWidth: 2,
                                  ),
                                )
                              : const Text('进入树洞'),
                        ),
                        const SizedBox(height: 12),
                        OutlinedButton(
                          onPressed: _loading
                              ? null
                              : () => Navigator.push(
                                    context,
                                    MaterialPageRoute(
                                      builder: (_) => const RegisterScreen(),
                                    ),
                                  ),
                          child: const Text('创建邮箱账号'),
                        ),
                        if (_message != null) ...[
                          const SizedBox(height: 14),
                          Text(
                            _message!,
                            textAlign: TextAlign.center,
                            style: TextStyle(
                              color: Theme.of(context).colorScheme.error,
                            ),
                          ),
                        ],
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 14),
                if (_enableDevPhoneLogin)
                  ExpansionTile(
                  tilePadding: const EdgeInsets.symmetric(horizontal: 8),
                  title: const Text('开发测试账号', style: TextStyle(fontSize: 14)),
                  subtitle: const Text(
                    '固定账号，仅用于开发兼容测试',
                    style: TextStyle(fontSize: 12),
                  ),
                  children: [
                    TimeEchoCard(
                      child: Column(
                        children: [
                          TextField(
                            controller: _phone,
                            readOnly: true,
                            keyboardType: TextInputType.phone,
                            decoration: const InputDecoration(labelText: '手机号'),
                          ),
                          const SizedBox(height: 10),
                          Row(
                            children: [
                              Expanded(
                                child: TextField(
                                  controller: _code,
                                  readOnly: true,
                                  decoration: const InputDecoration(
                                    labelText: '验证码',
                                  ),
                                ),
                              ),
                            ],
                          ),
                          const SizedBox(height: 12),
                          SizedBox(
                            width: double.infinity,
                            child: FilledButton.tonal(
                              onPressed: _loading ? null : _developmentLogin,
                              child: const Text('使用测试账号登录'),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _BrandHeader extends StatelessWidget {
  const _BrandHeader({required this.title, required this.subtitle});

  final String title;
  final String subtitle;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Container(
              width: 48,
              height: 48,
              decoration: BoxDecoration(
                gradient: const LinearGradient(
                  colors: [TimeEchoColors.duskPurple, Color(0xFF8CA7C8)],
                ),
                borderRadius: BorderRadius.circular(16),
              ),
              child: const Icon(Icons.air_rounded, color: Colors.white),
            ),
            const SizedBox(width: 12),
            const Text(
              'TimeEcho',
              style: TextStyle(
                fontSize: 24,
                fontWeight: FontWeight.w900,
                letterSpacing: -.5,
              ),
            ),
          ],
        ),
        const SizedBox(height: 28),
        Text(
          title,
          style: Theme.of(
            context,
          ).textTheme.headlineLarge?.copyWith(fontWeight: FontWeight.w900),
        ),
        if (subtitle.isNotEmpty) ...[
          const SizedBox(height: 8),
          Text(
            subtitle,
            style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                  color: TimeEchoColors.muted,
                  height: 1.5,
                ),
          ),
        ],
      ],
    );
  }
}
