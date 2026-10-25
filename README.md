# place

A collaborative 250×250 pixel canvas — an r/place clone — that originally ran on AWS
serverless (API Gateway WebSocket, four Lambdas, ElastiCache, SQS, S3, CloudFront) and now
runs as a four-container Docker Compose stack on a single small server.

Live demo: <https://place.jessexu.me> (nginx on the host terminates TLS with a Let's Encrypt
certificate; the stack itself only listens on `127.0.0.1:8090`).

![the app](docs/screenshot.png)

## What it is

You click a pixel, choose a colour, and hit **Place Pixel**. Everyone else connected to the
page sees it immediately. New visitors get the current drawing as a PNG, so the canvas
survives restarts and reloads. There is a 5 second per-browser cooldown, a 12-colour
palette plus a custom colour picker, and a brush mode for admins.

## Run it

```bash
cp .env.example .env         # then set PLACE_DATA_DIR to an absolute path
docker compose up -d
```

Open <http://localhost:8090>. One port serves the frontend, the WebSocket and the canvas
image; everything stateful lives on the host filesystem under `$PLACE_DATA_DIR`.

| variable | default | meaning |
|---|---|---|
| `PLACE_PORT` | `8090` | the single published host port |
| `PLACE_BIND` | `0.0.0.0` | bind address; use `127.0.0.1` behind a reverse proxy |
| `PLACE_DATA_DIR` | `./data` | host directory for `redis/` and `place/` |
| `PLACE_UID` / `PLACE_GID` | `1001` | owner of the files written into `PLACE_DATA_DIR` |
| `IMAGE_SIZE` | `250` | canvas edge in pixels |
| `RATE_LIMIT_SECONDS` | `5` | per-browser cooldown |
| `ADMIN_CLIENT_IDS` | empty | comma-separated browser ids that bypass the cooldown |

## Architecture

```mermaid
flowchart LR
    B[browser] -- HTTP --> G[gateway<br/>nginx]
    B <-- WebSocket --> G
    G -- "/ws" --> A[api<br/>FastAPI + uvicorn]
    G -- "/place.png" --> A
    A -- "clients, cooldowns, history" --> R[(redis<br/>valkey, AOF)]
    A -- "XADD place:events" --> R
    W[worker<br/>PNG writer] -- "XREADGROUP" --> R
    W -- "tmp + fsync + rename" --> P[[data/place/place.png]]
    A -- reads --> P
```

| service | role | state it owns |
|---|---|---|
| `gateway` | nginx: static frontend, `/ws` upgrade, `/place.png` proxy | none (config + static mounted read-only) |
| `api` | FastAPI: the whole WebSocket protocol, rate limiting, history | Redis keys, the `place:events` stream |
| `worker` | consumes the stream, applies pixels, writes the PNG | `data/place/place.png`, consumer group |
| `redis` | Valkey with AOF on a bind mount | `data/redis/` |

## AWS → Compose mapping

This is the same data model and the same wire protocol as the AWS version; only the hosting
changed. The original was retired because API Gateway + ElastiCache + NAT gateway costs
real money even when nobody is drawing.

| AWS (v3) | here | why it is equivalent |
|---|---|---|
| S3 static + CloudFront | `gateway` (nginx with a static dir) | one origin serves HTML, JS and the PNG |
| API Gateway WebSocket + routes | one `/ws` endpoint dispatching on the frame's `action` | same routing key (`$request.body.action`), same frames |
| `$connect` / `$disconnect` routes | on-accept / on-disconnect handlers | connection registry in Redis |
| Lambda `webSocketV1` | `api/place/app.py` | same handlers, same Redis keys, same cooldown maths |
| Lambda `placeBroadcaster` + `post_to_connection` | `api/place/hub.py` | in-process fan-out over live sockets |
| Lambda `savePlacePNG` + SQS `placePNG.fifo` | `worker` + Redis Stream consumer group | ordered, at-least-once, replayable |
| ElastiCache Valkey | `redis` (valkey image, AOF) | same commands, same key names |
| S3 `place.png` | `data/place/place.png` | durable "current image", written tmp+fsync+rename |
| Lambda `ziao-sqs-logger` + CloudWatch | stdout logs (`docker compose logs api`) | one log sink, no queue needed |
| VPC / NAT gateway / endpoints | the compose bridge network | isolation only, none of the cost |

The wire protocol is byte-identical to v3, so the frontend diff is tiny: the socket URL
became same-origin `/ws`, plus reconnect and a re-fetch of the PNG after a drop.

## Why these choices

- **One API process.** Connection state and fan-out live in a `Hub` dict, exactly like the
  Lambda did with API Gateway's connection registry. Two API replicas would each broadcast
  to their own clients only; scaling out would need Redis pub/sub. One process is enough for
  this workload and is honest about the trade-off.
- **Redis Streams instead of SQS.** `XADD` / `XREADGROUP` / `XACK` gives an ordered,
  at-least-once queue with a replayable consumer group, in the datastore that is already
  there. No broker container, no LocalStack.
- **The PNG is the durable canvas.** Clients load it on connect, so there is no history
  replay path to keep correct. The worker debounces writes to 4 per second and flushes on
  SIGTERM, so `docker compose restart` loses nothing.
- **nginx as the only ingress.** One published port carries both HTTP and the WebSocket
  upgrade; a TLS terminator in front of it can be added without touching the app.

## Repo map

```
api/            FastAPI app, the PNG worker, tests, smoke client
  place/        config, pixels, rate_limit, png_store, store, hub, app, worker
  tests/        36 tests (35 unit + 1 Redis integration)
gateway/        nginx.conf + the v3 frontend, patched to same-origin
docs/           architecture, deployment runbook, screenshot, legacy v3 sources
docker-compose.yml
```

`docs/legacy/` keeps the original AWS lambdas and frontend as submitted, for comparison —
the revival reuses their names and logic deliberately.

## Tests

```bash
docker compose run --rm --no-deps -v "$PWD/api:/app" -w /app api pytest -q
# 35 passed, 1 skipped
docker compose run --rm -e REDIS_URL_TEST=redis://redis:6379/0 \
  -v "$PWD/api:/app" -w /app api pytest -q
# 36 passed
```

The suite needs no Redis: `MemoryStore` implements the same protocol as `RedisStore`, and
one `@pytest.mark.integration` test exercises the real adapter.

## Deploying

See [docs/deploy.md](docs/deploy.md).
