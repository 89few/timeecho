# TimeEcho Backend

FastAPI 后端提供 PostgreSQL 持久化、Redis 匹配队列、WebSocket 实时消息、邮件验证码、媒体上传、通知中心和网页管理端。

## 启动

```powershell
docker compose up -d --build
docker compose ps
docker compose logs migrate
Invoke-RestMethod http://127.0.0.1:8000/health
```

Alembic 当前 head：`0014_temporary_password`。

## 关键安全约束

- 匿名纸飞机和即时遇见在交换名片前不返回真实用户 ID、昵称、头像、城市或主页入口。
- 双方名片同意状态在后端事务中处理，单方同意不暴露资料。
- 全局拉黑跨匹配、纸飞机、好友、私信和动态互动生效。
- 好友备注按用户单向保存，并应用于好友列表、主页和私信标题。
- 每个用户具有数据库唯一的 8 位不可修改 UID，后台和找人接口均可按 UID 精确检索。
- HTTP 与 WebSocket 发消息复用同一套 `client_message_id` 幂等保存逻辑。
- 匹配使用 Redis 分布式锁与数据库固定锁顺序，候选读取使用 `FOR UPDATE SKIP LOCKED`。
- 公开头像位于 `/app/app/static/uploads`；私聊和受限动态媒体位于 `/app/private_uploads`，由独立持久化卷保存并通过短期签名地址鉴权访问。
- Compose 对外端口只绑定 `127.0.0.1`；API 固定单容器、单 Uvicorn Worker。
- 生产配置拒绝默认密钥、默认管理员密码、开发验证码和社区模拟。

## 测试隔离

```powershell
python -m pytest -q
```

`tests/conftest.py` 在导入应用前覆盖环境并创建进程专属临时 SQLite。只有 SQLite 或数据库名以 `_test` 结尾的显式测试库会被接受；指向开发库时 pytest 会立即退出。

不要使用继承开发 `DATABASE_URL` 的容器命令运行测试。

## 生产覆盖

```powershell
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

启动前应通过环境或受保护的 `.env` 提供正式 JWT、加密、服务端盐、PostgreSQL、Redis、SMTP 和 Tunnel 配置。管理员使用 `scripts/create_admin.py` 创建到数据库，密码只保存哈希；不得把凭据写入源码、日志或 APK。

当前连接管理器是进程内存实现，因此生产文件显式限制为一个 API 实例和一个 Uvicorn Worker；多实例部署前需要 Redis Pub/Sub。

## 管理端

- 本地：<http://127.0.0.1:8000/admin>
- API 文档：<http://127.0.0.1:8000/docs>

生产环境不提供默认管理员凭据。
