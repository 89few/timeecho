# TimeEcho Flutter Android APP

这是 TimeEcho / 时光树洞的 Flutter Android 客户端，不是 WebView 包壳。

## 本机运行

```bash
cd mobile
flutter pub get
flutter analyze
flutter test
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000
```

安卓模拟器访问宿主机 FastAPI 使用 `http://10.0.2.2:8000`。
真机访问本机后端请使用电脑局域网 IP，例如：

```bash
flutter run --dart-define=API_BASE_URL=http://192.168.1.8:8000
```

## 打包 APK

```bash
flutter build apk --debug --dart-define=API_BASE_URL=http://10.0.2.2:8000
```

输出路径：

```text
mobile/build/app/outputs/flutter-apk/app-debug.apk
```

如果本机 Flutter 报 Android 平台文件不匹配，可在 mobile 目录执行：

```bash
flutter create --platforms=android .
flutter pub get
```

再重新构建。
