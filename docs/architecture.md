# Architecture

Four containers on one bridge network, one published port.

- **gateway** (nginx) — the only process with a host port. Serves the static frontend,
  upgrades `/ws` to the API, proxies `/place.png` and `/healthz`.
- **api** (FastAPI/uvicorn) — one process, one event loop. Owns the WebSocket protocol,
  the cooldown, the connection registry (`Hub`) and the history list. Writes stream events.
- **worker** — same image, different command (`python -m place.worker`). Reads the
  `place:events` stream through consumer group `png-writer`, applies pixels to an in-memory
  250×250 RGB buffer loaded from the PNG, and writes the PNG atomically at most 4×/second
  (and once more on SIGTERM).
- **redis** (valkey) — `connected_clients` (set), `drawing_history` (list, capped 5000),
  `rate_limit:<clientId>` (epoch-ms string with TTL), and the `place:events` stream.

## Rules that keep it simple

1. **Single writer per key.** `api` owns the client set, cooldowns and history. `worker`
   owns `place.png` and the consumer group. Nothing else writes either.
2. **`api` runs as one replica.** Fan-out is an in-process dict. >1 replica silently halves
   the audience; the fix is Redis pub/sub, not more replicas.
3. **The PNG is the source of truth for pixels.** The worker reloads it at startup, so a
   restart loses at most the last debounce window (~250 ms), and a flush on SIGTERM
   normally loses nothing.
4. **No named volumes.** Everything that must survive lives under `$PLACE_DATA_DIR`
   (`redis/`, `place/`), owned by `$PLACE_UID:$PLACE_GID`.
5. **History is advisory.** `getHistory` exists for parity with v3 but the frontend never
   asks for it; clients resync by re-fetching `place.png`.
