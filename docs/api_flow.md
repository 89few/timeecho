# API Flow

1. `POST /api/auth/send-code` 发送开发验证码。
2. `POST /api/auth/login` 用户 A 登录。
3. `POST /api/auth/login` 用户 B 登录。
4. 用户 A `POST /api/letters` 创建纸飞机，开发环境可传 `seal_seconds=3`。
5. 管理员 `POST /api/admin/maintenance/process-due-letters-once` 触发释放。
6. 用户 B `POST /api/salvage` 打捞。
7. 用户 B `POST /api/salvage/{letter_id}/reply` 创建临时会话。
8. 双方连接 `/ws/chat/{room_id}?token={access_token}`。
9. 任意一方 `POST /api/chat/rooms/{room_id}/exit` 销毁房间。
