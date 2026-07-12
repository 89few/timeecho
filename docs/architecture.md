# TimeEcho Architecture

```text
Flutter Android APP
  ├─ Auth / TokenStore / Dio API Client
  ├─ Letter / Salvage / Chat / User services
  └─ WebSocketChannel temporary anonymous chat
        ↓ HTTP + WS
FastAPI Backend
  ├─ JWT auth, phone hash + AES ciphertext
  ├─ Letters state machine: SEALED → AVAILABLE → SALVAGED → DESTROYED
  ├─ Redis ZSet delayed release queue
  ├─ Redis available pools by emotion/city
  ├─ WebSocket manager + offline message TTL
  ├─ Risk service + DB sensitive words + rate limit configs
  └─ Admin maintenance APIs
        ↓
PostgreSQL + Redis + Workers
```

## 匿名性设计

用户公开侧不展示手机号、内部 user_id、主页、好友、关注或粉丝。移动端只展示匿名代号，后端用户侧响应也避免返回 `author_id`、`salvaged_by`、`sender_id`、`user_a_id`、`user_b_id`。

## 部署边界

APK 只是 Flutter 客户端，FastAPI 后端需要通过 Docker Compose、本机服务或云服务器单独运行。
