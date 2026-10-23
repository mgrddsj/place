"""Cooldown decision, ported from handle_draw() in v3 webSocketV1."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Decision:
    allowed: bool
    next_available_ms: int


def evaluate(*, now_ms: int, stored_next_ms: int, cooldown_ms: int, whitelisted: bool) -> Decision:
    """Block while now < stored next-available; an allowed draw always opens a new window."""
    if not whitelisted and stored_next_ms and now_ms < stored_next_ms:
        return Decision(allowed=False, next_available_ms=stored_next_ms)
    return Decision(allowed=True, next_available_ms=now_ms + cooldown_ms)
