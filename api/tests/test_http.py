from place.png_store import PngCanvas


def test_healthz_reports_redis_and_online_count(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["redis"] is True
    assert body["online"] == 0


def test_place_png_is_404_before_the_worker_writes_one(client):
    assert client.get("/place.png").status_code == 404


def test_place_png_is_served_once_it_exists(client, settings):
    PngCanvas.blank(250).save_atomic(settings.place_png)
    response = client.get("/place.png")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content.startswith(b"\x89PNG\r\n\x1a\n")
