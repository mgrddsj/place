"""PNG writer: consumes the place:events stream, the port of v3 savePlacePNG + SQS."""
from __future__ import annotations

import asyncio
import logging
import signal
from pathlib import Path

from .config import Settings, load_settings
from .pixels import Draw, parse_draw
from .png_store import PngCanvas
from .store import RedisStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("place.worker")

CONSUMER_NAME = "png-writer-1"
BATCH_SIZE = 200
BLOCK_MS = 500
MIN_WRITE_INTERVAL_S = 0.25  # 4 PNG rewrites/second ceiling


def apply_batch(canvas: PngCanvas, messages: list[tuple[str, dict[str, str]]]) -> int:
    """Parse and apply one stream batch; unparsable messages are skipped, not fatal."""
    draws: list[Draw] = []
    for _message_id, fields in messages:
        try:
            payload = {key: int(value) for key, value in fields.items()}
        except (TypeError, ValueError):
            continue
        draw = parse_draw(payload, canvas.size)
        if draw is not None:
            draws.append(draw)
    return canvas.apply(draws)


def process_batch(
    canvas: PngCanvas, messages: list[tuple[str, dict[str, str]]], path: Path
) -> int:
    applied = apply_batch(canvas, messages)
    if applied:
        canvas.save_atomic(path)
    return applied


async def run(settings: Settings | None = None) -> None:
    settings = settings or load_settings()
    store = RedisStore(settings.redis_url, settings.events_stream)
    await store.ensure_group(settings.consumer_group)

    canvas = PngCanvas.load(settings.place_png, settings.image_size)
    if not settings.place_png.exists():
        canvas.save_atomic(settings.place_png)  # so /place.png is 200 from the first boot
        log.info("seeded blank canvas at %s", settings.place_png)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for name in ("SIGTERM", "SIGINT"):
        try:
            loop.add_signal_handler(getattr(signal, name), stop.set)
        except NotImplementedError:  # pragma: no cover - not reachable in the container
            pass

    log.info("worker started: image=%s size=%d", settings.place_png, settings.image_size)
    last_write = 0.0
    dirty = False
    while not stop.is_set():
        messages = await store.read_events(
            settings.consumer_group, CONSUMER_NAME, count=BATCH_SIZE, block_ms=BLOCK_MS
        )
        if messages:
            dirty = apply_batch(canvas, messages) > 0 or dirty
            await store.ack_events(
                settings.consumer_group, [message_id for message_id, _ in messages]
            )
        if dirty and (not messages or loop.time() - last_write >= MIN_WRITE_INTERVAL_S):
            canvas.save_atomic(settings.place_png)
            last_write = loop.time()
            dirty = False

    canvas.save_atomic(settings.place_png)
    await store.close()
    log.info("worker stopped, final image written")


if __name__ == "__main__":
    asyncio.run(run())
