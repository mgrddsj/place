"""Redis state, ported from v3 webSocketV1's ElastiCache usage.

Key names and shapes are identical to the AWS version:
  connected_clients  set   of connection ids
  drawing_history    list  of JSON strings, newest last
  rate_limit:<id>    str   epoch milliseconds of the next allowed draw
plus one Redis Stream (place:events) standing in for SQS placePNG.fifo.
"""
from __future__ import annotations

from typing import Protocol

from redis.asyncio import Redis

CLIENTS_KEY = "connected_clients"
HISTORY_KEY = "drawing_history"
HISTORY_LIMIT = 5000
EVENTS_MAXLEN = 100_000


class Store(Protocol):
    async def ping(self) -> bool: ...
    async def add_client(self, connection_id: str) -> None: ...
    async def remove_client(self, connection_id: str) -> None: ...
    async def clients(self) -> list[str]: ...
    async def get_cooldown(self, client_id: str) -> int: ...
    async def set_cooldown(self, client_id: str, next_ms: int, ttl_s: int) -> None: ...
    async def append_history(self, body: str) -> None: ...
    async def history(self, limit: int) -> list[str]: ...
    async def publish_event(self, fields: dict[str, str]) -> None: ...
    async def ensure_group(self, group: str) -> None: ...
    async def read_events(
        self, group: str, consumer: str, count: int, block_ms: int
    ) -> list[tuple[str, dict[str, str]]]: ...
    async def ack_events(self, group: str, ids: list[str]) -> None: ...
    async def close(self) -> None: ...


class RedisStore:
    def __init__(self, url: str, stream: str) -> None:
        self._redis = Redis.from_url(url, decode_responses=True)
        self._stream = stream

    async def ping(self) -> bool:
        try:
            return bool(await self._redis.ping())
        except Exception:  # noqa: BLE001 - a dead Redis must degrade, not crash /healthz
            return False

    async def add_client(self, connection_id: str) -> None:
        await self._redis.sadd(CLIENTS_KEY, connection_id)

    async def remove_client(self, connection_id: str) -> None:
        await self._redis.srem(CLIENTS_KEY, connection_id)

    async def clients(self) -> list[str]:
        return sorted(await self._redis.smembers(CLIENTS_KEY))

    async def get_cooldown(self, client_id: str) -> int:
        raw = await self._redis.get(f"rate_limit:{client_id}")
        return int(float(raw)) if raw else 0

    async def set_cooldown(self, client_id: str, next_ms: int, ttl_s: int) -> None:
        await self._redis.set(f"rate_limit:{client_id}", next_ms, ex=ttl_s)

    async def append_history(self, body: str) -> None:
        async with self._redis.pipeline(transaction=False) as pipe:
            pipe.rpush(HISTORY_KEY, body)
            pipe.ltrim(HISTORY_KEY, -HISTORY_LIMIT, -1)
            await pipe.execute()

    async def history(self, limit: int) -> list[str]:
        return await self._redis.lrange(HISTORY_KEY, -limit, -1)

    async def publish_event(self, fields: dict[str, str]) -> None:
        await self._redis.xadd(self._stream, fields, maxlen=EVENTS_MAXLEN, approximate=True)

    async def ensure_group(self, group: str) -> None:
        try:
            await self._redis.xgroup_create(self._stream, group, id="0", mkstream=True)
        except Exception as exc:  # noqa: BLE001 - BUSYGROUP is the normal path after first boot
            if "BUSYGROUP" not in str(exc):
                raise

    async def read_events(
        self, group: str, consumer: str, count: int, block_ms: int
    ) -> list[tuple[str, dict[str, str]]]:
        response = await self._redis.xreadgroup(
            group, consumer, {self._stream: ">"}, count=count, block=block_ms
        )
        events: list[tuple[str, dict[str, str]]] = []
        for _stream, messages in response or []:
            for message_id, fields in messages:
                events.append((message_id, fields))
        return events

    async def ack_events(self, group: str, ids: list[str]) -> None:
        if ids:
            await self._redis.xack(self._stream, group, *ids)

    async def close(self) -> None:
        await self._redis.aclose()


class MemoryStore:
    """In-process Store for tests; keeps the same semantics without a Redis."""

    def __init__(self) -> None:
        self._clients: set[str] = set()
        self._cooldowns: dict[str, int] = {}
        self._history: list[str] = []
        self._events: list[tuple[str, dict[str, str]]] = []
        self._sequence = 0

    async def ping(self) -> bool:
        return True

    async def add_client(self, connection_id: str) -> None:
        self._clients.add(connection_id)

    async def remove_client(self, connection_id: str) -> None:
        self._clients.discard(connection_id)

    async def clients(self) -> list[str]:
        return sorted(self._clients)

    async def get_cooldown(self, client_id: str) -> int:
        return self._cooldowns.get(client_id, 0)

    async def set_cooldown(self, client_id: str, next_ms: int, ttl_s: int) -> None:
        self._cooldowns[client_id] = next_ms

    async def append_history(self, body: str) -> None:
        self._history.append(body)
        del self._history[:-HISTORY_LIMIT]

    async def history(self, limit: int) -> list[str]:
        return self._history[-limit:] if limit else []

    async def publish_event(self, fields: dict[str, str]) -> None:
        self._sequence += 1
        self._events.append((f"{self._sequence}-0", dict(fields)))

    async def ensure_group(self, group: str) -> None:
        return None

    async def read_events(
        self, group: str, consumer: str, count: int, block_ms: int
    ) -> list[tuple[str, dict[str, str]]]:
        batch, self._events = self._events[:count], self._events[count:]
        return batch

    async def ack_events(self, group: str, ids: list[str]) -> None:
        return None

    async def close(self) -> None:
        return None
