import asyncio
import os

import pytest

from place.store import MemoryStore


def test_clients_roundtrip():
    async def scenario():
        store = MemoryStore()
        await store.add_client("a")
        await store.add_client("b")
        await store.remove_client("a")
        return await store.clients()

    assert asyncio.run(scenario()) == ["b"]


def test_history_is_trimmed_to_the_requested_window():
    async def scenario():
        store = MemoryStore()
        for index in range(5):
            await store.append_history(str(index))
        return await store.history(2)

    assert asyncio.run(scenario()) == ["3", "4"]


def test_cooldown_roundtrip():
    async def scenario():
        store = MemoryStore()
        await store.set_cooldown("client_x", 1234, ttl_s=65)
        return await store.get_cooldown("client_x"), await store.get_cooldown("nobody")

    assert asyncio.run(scenario()) == (1234, 0)


@pytest.mark.integration
def test_redis_store_against_live_valkey():
    from place.store import RedisStore

    url = os.environ.get("REDIS_URL_TEST")
    if not url:
        pytest.skip("set REDIS_URL_TEST to run against a live valkey")

    async def scenario():
        store = RedisStore(url, "place:test-events")
        await store.ensure_group("test-group")
        await store.add_client("conn_1")
        await store.set_cooldown("client_x", 999, ttl_s=60)
        await store.append_history('{"x":1}')
        await store.publish_event({"x": "1", "y": "2", "r": "3", "g": "4", "b": "5"})
        events = await store.read_events("test-group", "consumer-1", count=10, block_ms=200)
        cooldown = await store.get_cooldown("client_x")
        clients = await store.clients()
        history = await store.history(10)
        await store.ack_events("test-group", [event_id for event_id, _ in events])
        await store.remove_client("conn_1")
        await store.close()
        return cooldown, clients, history, events

    cooldown, clients, history, events = asyncio.run(scenario())
    assert cooldown == 999
    assert clients == ["conn_1"]
    assert history == ['{"x":1}']
    assert events and events[0][1]["x"] == "1"
