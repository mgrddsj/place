"""Two-client end-to-end check through the gateway.

Usage: python -m scripts.smoke_ws ws://gateway/ws
"""
import asyncio
import json
import sys
import uuid

import websockets

TARGET = {"x": 10, "y": 20, "r": 255, "g": 0, "b": 0}


async def _next_pixel(websocket, timeout: float = 5.0) -> dict:
    """Read frames until a pixel frame arrives (control frames are ignored)."""
    while True:
        frame = json.loads(await asyncio.wait_for(websocket.recv(), timeout))
        if "x" in frame and "y" in frame:
            return frame


async def main(url: str) -> int:
    client_id = f"smoke-{uuid.uuid4().hex[:8]}"  # fresh id: the cooldown must not bite
    async with websockets.connect(url) as first, websockets.connect(url) as second:
        await first.send(json.dumps({"action": "checkRateLimit", "clientId": client_id}))
        print("checkRateLimit ->", await first.recv())

        await first.send(json.dumps({"action": "draw", "clientId": client_id, **TARGET}))
        sender_pixel = await _next_pixel(first)
        other_pixel = await _next_pixel(second)
        print("sender saw  ->", sender_pixel)
        print("other saw   ->", other_pixel)

        ok = sender_pixel == TARGET and other_pixel == TARGET
        print("RESULT:", "PASS" if ok else "FAIL")
        return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "ws://127.0.0.1:8000/ws")))
