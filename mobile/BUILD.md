# Android 构建

交付真机 APK 使用 release + ABI 拆分，避免把调试运行时和三套 CPU 架构打进同一个包。

```powershell
$env:PUB_HOSTED_URL='https://pub.flutter-io.cn'
$env:FLUTTER_STORAGE_BASE_URL='https://storage.flutter-io.cn'
C:\dev\flutter\bin\flutter.bat build apk --release --split-per-abi `
  --dart-define=API_BASE_URL=https://你的后端域名
```

主流 Android 真机安装 `app-arm64-v8a-release.apk`。`app-debug.apk` 仅用于开发，
体积与内存占用均明显更高，不作为交付包。
