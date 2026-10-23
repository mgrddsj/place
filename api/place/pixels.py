"""Pixel payload validation, ported from v1 isValidSet + v3 savePlacePNG."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypeGuard


@dataclass(frozen=True)
class Draw:
    x: int
    y: int
    r: int
    g: int
    b: int

    def to_json(self) -> dict[str, int]:
        return {"x": self.x, "y": self.y, "r": self.r, "g": self.g, "b": self.b}


def _is_int(value: Any) -> TypeGuard[int]:
    # bool is a subclass of int; the browser never sends booleans here.
    return isinstance(value, int) and not isinstance(value, bool)


def parse_draw(payload: dict[str, Any], size: int) -> Draw | None:
    """Return a validated Draw, or None when any field is out of range or mistyped."""
    if not isinstance(payload, dict):
        return None

    x = payload.get("x")
    y = payload.get("y")
    r = payload.get("r")
    g = payload.get("g")
    b = payload.get("b")

    if not (_is_int(x) and _is_int(y) and _is_int(r) and _is_int(g) and _is_int(b)):
        return None
    if not (0 <= x < size and 0 <= y < size):
        return None
    if not all(0 <= channel <= 255 for channel in (r, g, b)):
        return None
    return Draw(x=x, y=y, r=r, g=g, b=b)
