# TimeEcho

TimeEcho 是一套温和、轻量的全栈社交应用：延时纸飞机、在线匿名匹配、好友私信、动态与通知中心。客户端使用 Flutter，后端使用 FastAPI、PostgreSQL、Redis、WebSocket 和 Docker Compose。

## 当前功能

- 邮箱注册、密码登录、限时一次性验证码、忘记密码与密码重置。
- 每个用户拥有创建后不可修改的唯一 8 位 UID；个人资料、找人和管理端均支持 UID。
- 个人头像、昵称、简介、好友申请、好友列表、长期私信和公开主页。
- 好友备注会同步用于好友列表、主页和私信标题；用户主页支持举报与全局拉黑。
- 动态支持文字、图片、视频、语音、可见范围、点赞、评论和作者删除。
- 消息页将好友申请、点赞、评论、会话通知与好友私信分组展示，并提供未读红点。
- 延时纸飞机发送、释放、打捞、回复、举报、结束会话和内容审核。
- 纸飞机及即时遇见使用房间级匿名身份；交换名片前，接口不会返回真实账号、昵称、头像或主页入口。
- 即时遇见支持倾诉/倾听/随便聊聊、话题偏好、取消、结束、重新匹配、拉黑和不再匹配。
- 双方都同意交换名片后才同时展示真实资料；交换成功后仍需单独发送好友申请。
- 全局拉黑会阻止再次匹配、纸飞机互动、好友申请、动态互动与私信。
- 消息使用 `client_message_id` 幂等，断线重试不会重复入库。
- 网页管理端采用桌面运营后台布局，提供 UID 检索、恢复/禁言/封禁、审核待办、用户与关系、内容治理、举报联动处置、敏感词及系统维护。
- 开发环境可保留 10 个社区账号，并通过延时 Worker 自然地参与公开动态互动。

客户端已移除城市采集与展示。

## 启动

在根目录双击 `start-backend.cmd`，或者运行：

```powershell
cd backend
docker compose up -d --build
docker compose ps
Invoke-RestMethod http://127.0.0.1:8000/health
```

本地入口：

- 产品页：<http://127.0.0.1:8000/>
- 管理端：<http://127.0.0.1:8000/admin>
- API 文档：<http://127.0.0.1:8000/docs>

迁移容器成功退出后，API 和 Worker 才会启动。现有 PostgreSQL 数据卷不会在正常重建中删除。

## 邮箱验证码

双击 `configure-email.cmd` 配置官方发件邮箱。脚本只把 SMTP 设置写入本机 `backend/.env`。SMTP 授权码通常不是邮箱网页登录密码，不要把它发送到聊天、提交到源码或写入 APK。

## 公网访问

`start-public-tunnel.cmd` 可启动临时 Cloudflare Quick Tunnel，但临时地址在 Tunnel 重建后可能变化。要让已安装 APK 长期使用同一个地址，需要在 Cloudflare 创建 Named Tunnel 和固定域名，再运行 `configure-stable-tunnel.cmd`。Tunnel token 和域名属于部署者账户，不能预置进源码或 APK。

生产覆盖文件为 `backend/docker-compose.prod.yml`。生产模式会关闭开发验证码和社区模拟，要求显式提供 JWT、加密、盐及管理员强凭据。PostgreSQL、Redis 和 API 的宿主端口均只绑定 `127.0.0.1`，Cloudflare 在 Compose 私有网络中访问 API。

当前 WebSocket 连接表保存在 API 进程内，因此受支持的部署拓扑是一个 API 容器、一个 Uvicorn Worker。扩展到多实例前需接入 Redis Pub/Sub。

## 开发与测试

```powershell
cd backend
python -m pytest -q

cd ..\mobile
flutter analyze
flutter test
```

pytest 在导入应用前强制切换到独立的临时 SQLite；如果 `DATABASE_URL` 不是 SQLite 或数据库名不以 `_test` 结尾，测试会立即拒绝运行，避免误删开发数据。

数据库当前迁移版本为 `0014_temporary_password`。公开头像由 `uploads_data` 持久化；私聊图片、语音、视频和受限动态媒体由 `private_media_data` 持久化，并通过鉴权后的短期签名地址访问。

消息页使用 `/api/overview/messages` 一次取得会话、互动通知和好友申请；公开主页资料与动态并行加载，主要列表查询采用批量加载并启用 GZip 响应压缩。

正式 APK 使用构建时固定的 API 地址，不在登录页或设置页暴露部署地址。只有显式使用 `--dart-define=ALLOW_BACKEND_OVERRIDE=true` 的开发构建才允许切换地址。

## APK 构建

```powershell
cd mobile
flutter build apk --release --target-platform android-arm64 --split-per-abi `
  --dart-define=API_BASE_URL=https://你的固定域名
```

交付 APK 使用测试签名，仅适合侧载验收。正式上架前必须创建并安全备份自己的 release keystore。

## 已知限制

- APP 进程被系统彻底杀死后仍要接收远程通知，需要 FCM 或手机厂商推送及其云端凭据；当前本地通知覆盖 APP 运行期间。
- Quick Tunnel 不是稳定生产地址；固定直连需要 Named Tunnel/域名。
- WebSocket 暂限单 API 实例和单 Worker。

## 目录

```text
backend/  FastAPI、迁移、Worker、管理端、测试与 Docker Compose
mobile/   Flutter Android 客户端
docs/     架构和补充说明
```

生产部署、安全边界和首次管理员创建见 [docs/production-deployment.md](docs/production-deployment.md) 与 [SECURITY.md](SECURITY.md)。仓库不包含 `.env`、数据库、用户上传内容、签名密钥或 APK。
