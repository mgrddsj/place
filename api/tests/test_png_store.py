import png

from place.pixels import Draw
from place.png_store import PngCanvas


def _read_pixel(path, x, y):
    width, height, rows, _info = png.Reader(filename=str(path)).asRGB()
    row = list(rows)[y]
    return tuple(row[x * 3: x * 3 + 3])


def test_blank_canvas_is_white_250x250(tmp_path):
    path = tmp_path / "place.png"
    PngCanvas.blank(250).save_atomic(path)
    width, height, rows, _info = png.Reader(filename=str(path)).asRGB()
    assert (width, height) == (250, 250)
    assert tuple(list(rows)[0][:3]) == (255, 255, 255)


def test_apply_then_save_roundtrip(tmp_path):
    path = tmp_path / "place.png"
    canvas = PngCanvas.blank(250)
    canvas.apply([Draw(x=3, y=4, r=10, g=20, b=30)])
    canvas.save_atomic(path)
    assert _read_pixel(path, 3, 4) == (10, 20, 30)
    assert _read_pixel(path, 4, 4) == (255, 255, 255)


def test_load_existing_image_then_apply(tmp_path):
    path = tmp_path / "place.png"
    first = PngCanvas.blank(250)
    first.apply([Draw(1, 1, 9, 9, 9)])
    first.save_atomic(path)
    reloaded = PngCanvas.load(path, 250)
    reloaded.apply([Draw(1, 1, 200, 100, 50)])
    reloaded.save_atomic(path)
    assert _read_pixel(path, 1, 1) == (200, 100, 50)


def test_load_missing_file_returns_blank(tmp_path):
    canvas = PngCanvas.load(tmp_path / "nope.png", 250)
    assert canvas.apply([Draw(0, 0, 0, 0, 0)]) == 1


def test_save_leaves_no_temp_file(tmp_path):
    path = tmp_path / "place.png"
    PngCanvas.blank(250).save_atomic(path)
    assert sorted(item.name for item in tmp_path.iterdir()) == ["place.png"]
