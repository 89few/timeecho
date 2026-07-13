from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import admin, auth, chat, letters, matching, media, notifications, overview, reports, salvage, social, users
from app.core.config import settings
from app.core.dependencies import ensure_user_can_post
from app.core.exceptions import AppException, app_exception_handler, generic_exception_handler
from app.core.security import decode_token
from app.db.session import AsyncSessionLocal, close_resources, redis_client
from app.models.chat import ChatRoom, ChatRoomKind, ChatRoomStatus
from app.models.user import User
from app.models.security import AdminAuditLog
from app.core.security import utcnow
from app.services.chat_service import get_active_room_for_user, mark_message_read, mark_messages_read, save_chat_message, validate_chat_message_input
from app.services.anonymous_identity_service import sender_display_name
from app.services.matching_service import disconnect_waiter, heartbeat as matching_heartbeat
from app.services.media_service import signed_media_url
from app.websocket.manager import manager, matching_manager

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await close_resources()


app = FastAPI(title=settings.app_name, debug=settings.debug, lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=500, compresslevel=5)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.add_exception_handler(AppException, app_exception_handler)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "error_code": "VALIDATION_ERROR",
            "message": "请求参数不正确",
            "details": exc.errors(),
        },
    )


app.add_exception_handler(Exception, generic_exception_handler)


@app.middleware("http")
async def admin_audit_middleware(request, call_next):
    response = await call_next(request)
    admin = getattr(request.state, "admin", None)
    path = request.url.path
    sensitive_read = request.method == "GET" and (
        "/api/admin/complaints" in path or "/api/admin/reviews" in path
    )
    if admin and (request.method != "GET" or sensitive_read) and not path.endswith("/logout"):
        try:
            async with AsyncSessionLocal() as audit_db:
                audit_db.add(
                    AdminAuditLog(
                        admin_id=admin.id,
                        action=f"{request.method} {path}",
                        target_type=path.split("/")[3] if len(path.split("/")) > 3 else None,
                        target_id=path.rsplit("/", 1)[-1] if path.rsplit("/", 1)[-1].isdigit() else None,
                        after_json=json.dumps({"status_code": response.status_code}),
                        ip_address=request.client.host if request.client else None,
                        user_agent=request.headers.get("user-agent"),
                        created_at=utcnow(),
                    )
                )
                await audit_db.commit()
        except Exception:
            logger.exception("admin audit write failed")
    return response


@app.middleware("http")
async def media_cache_headers(request, call_next):
    response = await call_next(request)
    if request.url.path == "/admin" or request.url.path.endswith("/admin.js"):
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"
        response.headers["X-Frame-Options"] = "DENY"
    if request.url.path.startswith("/static/uploads/") or request.url.path.startswith("/static/assets/avatars/"):
        response.headers["Cache-Control"] = "public, max-age=604800, immutable"
    return response

app.include_router(auth.router, prefix=settings.api_prefix)
app.include_router(users.router, prefix=settings.api_prefix)
app.include_router(letters.router, prefix=settings.api_prefix)
app.include_router(salvage.router, prefix=settings.api_prefix)
app.include_router(chat.router, prefix=settings.api_prefix)
app.include_router(reports.router, prefix=settings.api_prefix)
app.include_router(admin.router, prefix=settings.api_prefix)
app.include_router(social.router, prefix=settings.api_prefix)
app.include_router(notifications.router, prefix=settings.api_prefix)
app.include_router(overview.router, prefix=settings.api_prefix)
app.include_router(media.router, prefix=settings.api_prefix)
app.include_router(matching.router, prefix=settings.api_prefix)


@app.get("/")
async def landing():
    return RedirectResponse(url="/admin", status_code=307)


@app.get("/app")
async def web_app():
    return FileResponse("app/static/app.html")


@app.get("/admin")
async def admin_app():
    return FileResponse("app/static/admin.html")


@app.get("/health")
async def health():
    return {"success": True, "data": {"status": "ok"}, "message": "ok"}


async def _get_ws_user(db: AsyncSession, ticket: str) -> User:
    key = f"ws:ticket:{ticket}"
    raw_user_id = await redis_client.get(key)
    if not raw_user_id:
        raise AppException("INVALID_WS_TICKET", "连接凭证无效或已过期", 401)
    consumed = await redis_client.eval(
        "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end",
        1, key, str(raw_user_id),
    )
    if not consumed:
        raise AppException("INVALID_WS_TICKET", "连接凭证已使用", 401)
    user = await db.get(User, int(raw_user_id))
    if not user:
        raise AppException("USER_NOT_FOUND", "用户不存在", 404)
    ensure_user_can_post(user)
    return user


@app.websocket("/ws/matching")
async def matching_ws(websocket: WebSocket, ticket: str):
    async with AsyncSessionLocal() as db:
        try:
            user = await _get_ws_user(db, ticket)
            await matching_manager.connect(0, user.id, websocket)
            await websocket.send_json({"type": "ready"})
            while True:
                payload = await websocket.receive_json()
                if payload.get("type") == "heartbeat":
                    await matching_heartbeat(db, redis_client, user)
                    await websocket.send_json({"type": "heartbeat_ack"})
        except WebSocketDisconnect:
            pass
        except AppException as exc:
            await websocket.close(code=4400, reason=exc.message)
        finally:
            if "user" in locals():
                matching_manager.disconnect(0, user.id)
                await disconnect_waiter(db, redis_client, user)


@app.websocket("/ws/chat/{room_id}")
async def chat_ws(websocket: WebSocket, room_id: int, ticket: str):
    async with AsyncSessionLocal() as db:
        try:
            user = await _get_ws_user(db, ticket)
            room = await get_active_room_for_user(db, room_id, user.id)
            await manager.connect(room_id, user.id, websocket)

            await mark_messages_read(db, room_id, user.id)

            offline_key = f"chat:offline:{room_id}:{user.id}"
            cached = await redis_client.lrange(offline_key, 0, -1)
            if cached:
                for item in cached:
                    try:
                        payload = json.loads(item)
                    except json.JSONDecodeError:
                        payload = {"type": "message", "content": item}
                    await websocket.send_json(payload)
                    if payload.get("message_id"):
                        await mark_message_read(db, int(payload["message_id"]))
                await redis_client.delete(offline_key)

            while True:
                payload = await websocket.receive_json()
                if payload.get("type") != "message":
                    await websocket.send_json({"type": "error", "message": "不支持的消息类型"})
                    continue
                try:
                    room = await get_active_room_for_user(db, room_id, user.id)
                    kind, content, media_url = validate_chat_message_input(
                        room,
                        str(payload.get("kind") or "text"),
                        str(payload.get("content") or ""),
                        str(payload.get("media_url") or "") or None,
                    )
                    msg, unread_count, created = await save_chat_message(
                        db,
                        redis_client,
                        room,
                        user,
                        content,
                        kind=kind,
                        media_url=media_url,
                        client_message_id=payload.get("client_message_id"),
                    )
                except AppException as exc:
                    await websocket.send_json({
                        "type": (
                            "blocked"
                            if exc.error_code in {"MESSAGE_BLOCKED", "USER_BLOCKED"}
                            else "error"
                        ),
                        "error_code": exc.error_code,
                        "message": exc.message,
                    })
                    continue

                recipient_id = room.user_b_id if user.id == room.user_a_id else room.user_a_id
                message_payload = {
                    "type": "message",
                    "room_id": room.id,
                    "message_id": msg.id,
                    "client_message_id": msg.client_message_id,
                    "sender_name": await sender_display_name(db, room, user),
                    "sender_role": "peer",
                    "content": content,
                    "kind": kind,
                    "media_url": signed_media_url(media_url, recipient_id),
                    "created_at": msg.created_at.isoformat(),
                }
                if created:
                    sent = await manager.send_to_user(room.id, recipient_id, message_payload)
                    if sent:
                        await mark_message_read(db, msg.id)
                    else:
                        offline_key = f"chat:offline:{room.id}:{recipient_id}"
                        await redis_client.rpush(offline_key, json.dumps(message_payload, ensure_ascii=False))
                        await redis_client.expire(offline_key, 60 * 60 * 12)
                await websocket.send_json({
                    "type": "ack",
                    "message_id": msg.id,
                    "client_message_id": msg.client_message_id,
                    "duplicate": not created,
                })
                if unread_count >= 5:
                    await websocket.send_json({"type": "system", "message": "对方暂时没有回应，建议停止发送。"})
        except WebSocketDisconnect:
            manager.disconnect(room_id, locals().get("user", type("U", (), {"id": 0})()).id)
        except AppException as exc:
            await websocket.close(code=4400, reason=exc.message)
        except Exception:
            logger.exception("websocket internal error")
            await websocket.close(code=1011, reason="internal error")
        finally:
            if "user" in locals():
                manager.disconnect(room_id, user.id)
                if "room" in locals() and room.room_kind != ChatRoomKind.FRIEND:
                    current_room = await db.get(ChatRoom, room_id)
                    if current_room and current_room.status == ChatRoomStatus.ACTIVE:
                        peer_id = (
                            current_room.user_b_id
                            if user.id == current_room.user_a_id
                            else current_room.user_a_id
                        )
                        await manager.send_to_user(
                            room_id,
                            peer_id,
                            {
                                "type": "partner_left",
                                "room_id": room_id,
                                "message": "对方暂时离开了聊天室",
                            },
                        )
