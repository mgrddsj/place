"""The durable 'current image' store, ported from v3 savePlacePNG."""
from __future__ import annotations

import os
from io import BytesIO
from pathlib import Path
from typing import Iterable

import png

from .pixels import Draw


class PngCanvas:
    """A 250x250 8-bit RGB canvas backed by a PNG file."""

    def __init__(self, size: int, rows: list[list[int]]) -> None:
        self.size = size
        self._rows = rows

    @classmethod
    def blank(cls, size: int) -> "PngCanvas":
        return cls(size, [[255] * (size * 3) for _ in range(size)])

    @classmethod
    def load(cls, path: Path, size: int) -> "PngCanvas":
        """Load an existing PNG; missing or unreadable means start white (as in savePlacePNG)."""
        try:
            width, height, rows, _info = png.Reader(filename=str(path)).asRGB()
        except (OSError, png.Error, ValueError):
            return cls.blank(size)
        if width != size or height != size:
            return cls.blank(size)
        return cls(size, [list(row) for row in rows])

    def apply(self, draws: Iterable[Draw]) -> int:
        applied = 0
        for draw in draws:
            offset = draw.x * 3
            row = self._rows[draw.y]
            row[offset] = draw.r
            row[offset + 1] = draw.g
            row[offset + 2] = draw.b
            applied += 1
        return applied

    def to_bytes(self) -> bytes:
        buffer = BytesIO()
        writer = png.Writer(
            width=self.size,
            height=self.size,
            greyscale=False,
            alpha=False,
            compression=1,
        )
        writer.write(buffer, self._rows)
        return buffer.getvalue()

    def save_atomic(self, path: Path) -> None:
        """Write to a sibling temp file, fsync, then rename: readers never see a partial PNG."""
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        with tmp.open("wb") as handle:
            handle.write(self.to_bytes())
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
