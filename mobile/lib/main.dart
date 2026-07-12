import 'package:flutter/material.dart';

import 'app.dart';
import 'core/app_config.dart';
import 'core/app_notification_service.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await AppConfig.load();
  await AppNotificationService.instance.initialize();
  runApp(const TimeEchoApp());
}
