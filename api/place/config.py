"""Environment-driven configuration for the revived place service."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return default if raw in (None, "") else int(raw)


@dataclass(frozen=True)
class Settings:
    image_size: int
    rate_limit_seconds: int
    admin_client_ids: frozenset[str]
    redis_url: str
    data_dir: Path
    events_stream: str
    consumer_group: str

    @property
    def place_png(self) -> Path:
        return self.data_dir / "place.png"

    @property
    def cooldown_ms(self) -> int:
        return self.rate_limit_seconds * 1000


def load_settings() -> Settings:
    admins = os.environ.get("ADMIN_CLIENT_IDS", "")
    return Settings(
        image_size=_int("IMAGE_SIZE", 250),
        rate_limit_seconds=_int("RATE_LIMIT_SECONDS", 5),
        admin_client_ids=frozenset(x.strip() for x in admins.split(",") if x.strip()),
        redis_url=os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0"),
        data_dir=Path(os.environ.get("DATA_DIR", "./data")),
        events_stream=os.environ.get("EVENTS_STREAM", "place:events"),
        consumer_group=os.environ.get("CONSUMER_GROUP", "png-writer"),
    )
