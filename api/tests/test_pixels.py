import pytest

from place.pixels import Draw, parse_draw


def test_accepts_valid_draw():
    assert parse_draw({"x": 0, "y": 249, "r": 0, "g": 255, "b": 12}, 250) == Draw(0, 249, 0, 255, 12)


@pytest.mark.parametrize("payload", [
    {"x": -1, "y": 0, "r": 0, "g": 0, "b": 0},
    {"x": 250, "y": 0, "r": 0, "g": 0, "b": 0},
    {"x": 0, "y": 250, "r": 0, "g": 0, "b": 0},
    {"x": 0, "y": 0, "r": 256, "g": 0, "b": 0},
    {"x": 0, "y": 0, "r": -1, "g": 0, "b": 0},
    {"x": 1.5, "y": 0, "r": 0, "g": 0, "b": 0},
    {"x": "1", "y": 0, "r": 0, "g": 0, "b": 0},
    {"x": True, "y": 0, "r": 0, "g": 0, "b": 0},
    {"x": 0, "y": 0, "r": 0, "g": 0},
    {},
])
def test_rejects_invalid_draw(payload):
    assert parse_draw(payload, 250) is None
