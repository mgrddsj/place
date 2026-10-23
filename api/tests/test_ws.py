def _draw(client_id, x=5, y=6, r=255, g=0, b=0):
    return {"action": "draw", "clientId": client_id, "x": x, "y": y, "r": r, "g": g, "b": b}


def test_broadcast_reaches_sender_and_other_clients(client):
    with client.websocket_connect("/ws") as first, client.websocket_connect("/ws") as second:
        first.send_json(_draw("client_a"))
        assert first.receive_json() == {"x": 5, "y": 6, "r": 255, "g": 0, "b": 0}
        ack = first.receive_json()
        assert ack["type"] == "rateLimit"
        assert ack["nextAvailableTime"] > 0
        assert second.receive_json() == {"x": 5, "y": 6, "r": 255, "g": 0, "b": 0}


def test_second_draw_within_cooldown_is_rejected(client):
    with client.websocket_connect("/ws") as websocket:
        websocket.send_json(_draw("client_b"))
        websocket.receive_json()
        websocket.receive_json()
        websocket.send_json(_draw("client_b", x=7))
        error = websocket.receive_json()
        assert error["type"] == "error"
        assert error["error"] == "rate_limited"
        assert error["nextAvailableTime"] > 0


def test_admin_client_bypasses_cooldown(client):
    with client.websocket_connect("/ws") as websocket:
        websocket.send_json(_draw("client_admin"))
        websocket.receive_json()
        websocket.receive_json()
        websocket.send_json(_draw("client_admin", x=8))
        assert websocket.receive_json() == {"x": 8, "y": 6, "r": 255, "g": 0, "b": 0}


def test_out_of_bounds_pixel_is_rejected(client):
    with client.websocket_connect("/ws") as websocket:
        websocket.send_json(_draw("client_c", x=999))
        assert websocket.receive_json()["error"] == "invalid_draw"


def test_unknown_action_is_rejected(client):
    with client.websocket_connect("/ws") as websocket:
        websocket.send_json({"action": "nope"})
        assert websocket.receive_json()["error"] == "unknown_action"


def test_history_returns_past_draws(client):
    with client.websocket_connect("/ws") as websocket:
        websocket.send_json(_draw("client_d"))
        websocket.receive_json()
        websocket.receive_json()
        websocket.send_json({"action": "getHistory"})
        message = websocket.receive_json()
        assert message["type"] == "history"
        assert message["events"] == [{"x": 5, "y": 6, "r": 255, "g": 0, "b": 0}]


def test_check_rate_limit_starts_at_zero(client):
    with client.websocket_connect("/ws") as websocket:
        websocket.send_json({"action": "checkRateLimit", "clientId": "client_e"})
        assert websocket.receive_json() == {"type": "rateLimit", "nextAvailableTime": 0}
