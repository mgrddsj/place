"""In-process fan-out: the replacement for API Gateway post_to_connection."""
from __future__ import annotations

import asyncio

from fastapi import WebSocket


class Hub:
    def __init__(self) -> None:
        self._connections: dict[str, WebSocket] = {}

    def add(self, connection_id: str, websocket: WebSocket) -> None:
        self._connections[connection_id] = websocket

    def remove(self, connection_id: str) -> None:
        self._connections.pop(connection_id, None)

    def ids(self) -> list[str]:
        return list(self._connections)

    async def broadcast(self, message: str) -> int:
        """Send to every live socket; drop the ones that raise (stale clients)."""
        targets = list(self._connections.items())
        results = await asyncio.gather(
            *(websocket.send_text(message) for _cid, websocket in targets),
            return_exceptions=True,
        )
        sent = 0
        for (connection_id, _websocket), result in zip(targets, results, strict=True):
            if isinstance(result, Exception):
                self.remove(connection_id)
            else:
                sent += 1
        return sent
