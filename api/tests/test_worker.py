import png

from place.png_store import PngCanvas
from place.worker import apply_batch, process_batch


def _message(**fields):
    return ("1-0", {key: str(value) for key, value in fields.items()})


def test_apply_batch_ignores_junk_messages():
    canvas = PngCanvas.blank(250)
    assert apply_batch(canvas, [("1-0", {"x": "nan", "y": "0", "r": "0", "g": "0", "b": "0"})]) == 0
    assert apply_batch(canvas, []) == 0


def test_process_batch_writes_the_png(tmp_path):
    path = tmp_path / "place.png"
    canvas = PngCanvas.blank(250)
    applied = process_batch(canvas, [_message(x=2, y=3, r=1, g=2, b=3)], path)
    assert applied == 1
    assert path.exists()
    _width, _height, rows, _info = png.Reader(filename=str(path)).asRGB()
    assert tuple(list(rows)[3][6:9]) == (1, 2, 3)
