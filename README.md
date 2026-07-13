# TimeEcho

TimeEcho 是一个面向匿名社交场景的全栈工程示例，采用 Flutter 客户端、FastAPI 异步 API、PostgreSQL、Redis、WebSocket 与 Docker Compose。

## 系统架构

```text
Flutter Android
  ├─ REST / JWT + refresh rotation
  ├─ one-time WebSocket ticket
  └─ secure storage / local cache
            │ HTTPS / WSS
            ▼
Cloudflare Tunnel
            │ Docker private network
            ▼
FastAPI (single Uvicorn worker)
  ├─ API routers ─ services ─ SQLAlchemy async ─ PostgreSQL
  ├─ WebSocket connection manager
  ├─ Redis queue / lock / rate limit / ephemeral state
  ├─ Alembic migrations
  └─ background workers
       ├─ delayed-letter release
       ├─ expired-content cleanup
       ├─ dormant-account processing
       └─ optional community interaction
```

生产 Compose 将 PostgreSQL、Redis 和 API 宿主端口绑定到 `127.0.0.1`；公网流量只通过 HTTPS Tunnel 进入。上传文件和数据库使用独立持久化 Volume。

## 技术栈

| 层级 | 主要技术 |
| --- | --- |
| 移动端 | Flutter 3 / Dart 3、Dio、web_socket_channel、flutter_secure_storage、cached_network_image、image_picker、record、audioplayers、video_player |
| API | Python 3.12、FastAPI、Pydantic v2、Uvicorn |
| 数据访问 | SQLAlchemy 2.0 Async、asyncpg、Alembic |
| 数据与状态 | PostgreSQL 16、Redis 7 |
| 实时通信 | WebSocket、一次性 Ticket、离线消息缓存、`client_message_id` 幂等 |
| 安全 | JWT access/refresh、刷新令牌轮换、bcrypt、AES-GCM、HttpOnly 管理员会话、RBAC、审计日志 |
| 运维 | Docker Compose、Cloudflare Tunnel、健康检查、持久化 Volume、后台 Worker |
| 测试 | pytest、pytest-asyncio、HTTPX、SQLite 隔离库、Flutter test/analyze |

## 后端分层

```text
backend/app/
├─ api/          HTTP 路由、鉴权依赖与输入输出边界
├─ core/         配置、安全、加密、异常和公共常量
├─ db/           AsyncSession、Redis 生命周期和数据库基类
├─ models/       SQLAlchemy 领域模型
├─ schemas/      Pydantic 请求与响应模型
├─ services/     匹配、聊天、匿名身份、社交关系与媒体业务逻辑
├─ websocket/    房间连接管理和实时事件分发
├─ workers/      延时任务、清理任务及可选社区互动
└─ static/       管理后台静态资源
```

API 路由不信任客户端传入的 `user_id`，身份与资源权限均从当前 JWT 或管理员会话解析。业务规则集中在 services 层，使 HTTP 与 WebSocket 消息发送复用同一套权限和幂等逻辑。

## 关键工程设计

### 匿名关系与名片交换

匿名身份绑定到会话关系而非用户全局账号。同一房间身份稳定，不同房间无法据此关联同一用户。交换名片使用双方同意状态和数据库事务；双方都确认前，API 与 WebSocket DTO 不返回真实 UID、昵称、头像或主页入口。

### 并发匹配

Redis 保存等待队列、心跳和短期匹配状态，数据库保存房间、参与者、屏蔽关系及最近匹配记录。固定锁顺序与原子状态变更用于避免重复入队、多房间和并发重复匹配。

### 消息一致性

消息表对 `(room_id, sender_id, client_message_id)` 建立唯一约束。HTTP 与 WebSocket 均调用统一保存服务，客户端断线重试不会重复入库。临时状态和离线推送缓存在 Redis，持久消息落入 PostgreSQL。

### 认证与管理后台

- 用户使用 access/refresh 双 Token、`jti` 会话记录和 refresh rotation；封禁、改密或注销可撤销全部会话。
- Flutter Token 保存于系统安全存储，不写入 SharedPreferences。
- WebSocket 使用短期一次性 Ticket，不把完整 JWT 放进 URL。
- 管理员独立建表，密码哈希存储，支持 RBAC、失败锁定、服务端会话撤销和操作审计。
- 管理端通过 HttpOnly、Secure、SameSite Cookie 鉴权，不在 localStorage 保存 Token。

### 数据与媒体安全

聊天和纸飞机正文使用带密钥版本的 AES-GCM 密文。公开头像与私密媒体分目录存储；私聊图片、语音、视频及受限动态通过权限检查后的短期签名地址访问。生产日志不得记录邮箱、手机号、正文或凭据。

## 数据库迁移

迁移位于 `backend/alembic/versions/`，当前版本：

```text
0001_initial → ... → 0014_temporary_password
```

主要演进包括邮箱认证、社交关系、匿名匹配、全局拉黑、消息幂等、管理员与用户会话、私密媒体、审核证据和临时密码。

## 本地开发

准备 `backend/.env`：

```powershell
Copy-Item backend/.env.example backend/.env
```

启动完整依赖：

```powershell
cd backend
docker compose up -d --build
docker compose ps
Invoke-RestMethod http://127.0.0.1:8000/health
```

入口：

- 管理端：<http://127.0.0.1:8000/admin>
- OpenAPI：<http://127.0.0.1:8000/docs>
- 健康检查：<http://127.0.0.1:8000/health>

根路径 `/` 会重定向到管理端。首次管理员通过 `backend/scripts/create_admin.py` 创建，禁止在生产环境保留默认密码。

## 测试

```powershell
cd backend
python -m pytest -q

cd ../mobile
flutter analyze
flutter test
```

pytest 会在导入应用前强制使用独立 SQLite 或名称以 `_test` 结尾的数据库；检测到开发/生产数据库时立即拒绝运行。

## 生产部署

生产环境必须同时加载基础 Compose 和生产覆盖：

```bash
cd backend
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T api alembic upgrade head
```

生产配置会拒绝默认 JWT、加密密钥、固定验证码和自动手机号注册。社区互动 Worker 由 `COMMUNITY_SIMULATION_ENABLED` 显式控制；公开部署前应根据平台规范决定是否启用并向用户披露自动化账号。

详细部署和安全边界见 [docs/production-deployment.md](docs/production-deployment.md) 与 [SECURITY.md](SECURITY.md)。

## Flutter 构建

```powershell
cd mobile
flutter build apk --release --target-platform android-arm64 --split-per-abi `
  --dart-define=API_BASE_URL=https://api.example.com `
  --dart-define=API_DISCOVERY_URL=https://example.com/endpoint.json
```

仓库中的 Android 配置可直接构建；`mobile/android/local.properties` 属于机器文件，不提交。正式发布前需配置并安全保存自己的 release keystore。

## License

[MIT](LICENSE)
