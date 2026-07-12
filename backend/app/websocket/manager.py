from __future__ import annotations

from collections import defaultdict

from fastapi import WebSocket, WebSocketDisconnect


class ConnectionManager:
    def __init__(self) -> None:
        self.active: dict[int, dict[int, WebSocket]] = defaultdict(dict)

    async def connect(self, room_id: int, user_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active[room_id][user_id] = websocket

    def disconnect(self, room_id: int, user_id: int) -> None:
        if room_id in self.active and user_id in self.active[room_id]:
            self.active[room_id].pop(user_id, None)
        if room_id in self.active and not self.active[room_id]:
            self.active.pop(room_id, None)

    async def send_to_user(self, room_id: int, user_id: int, payload: dict) -> bool:
        websocket = self.active.get(room_id, {}).get(user_id)
        if not websocket:
            return False
        try:
            await websocket.send_json(payload)
            return True
        except (OSError, RuntimeError, WebSocketDisconnect):
            # A peer can close between the in-memory lookup and the send.  Treat
            # that race as an offline delivery instead of failing the sender's
            # socket/finalizer.
            self.disconnect(room_id, user_id)
            return False

    async def broadcast_room(self, room_id: int, payload: dict) -> None:
        for user_id in list(self.active.get(room_id, {})):
            await self.send_to_user(room_id, user_id, payload)

    async def disconnect_user(self, user_id: int, code: int = 4403) -> None:
        for room_id, users in list(self.active.items()):
            websocket = users.get(user_id)
            if websocket:
                try:
                    await websocket.close(code=code)
                except (OSError, RuntimeError):
                    pass
                self.disconnect(room_id, user_id)


manager = ConnectionManager()
matching_manager = ConnectionManager()
