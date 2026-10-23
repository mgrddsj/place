from place.rate_limit import evaluate


def test_first_draw_is_allowed_and_opens_window():
    decision = evaluate(now_ms=1_000, stored_next_ms=0, cooldown_ms=5_000, whitelisted=False)
    assert decision.allowed is True
    assert decision.next_available_ms == 6_000


def test_second_draw_inside_window_is_blocked():
    decision = evaluate(now_ms=4_000, stored_next_ms=6_000, cooldown_ms=5_000, whitelisted=False)
    assert decision.allowed is False
    assert decision.next_available_ms == 6_000


def test_draw_after_window_is_allowed():
    assert evaluate(now_ms=6_001, stored_next_ms=6_000, cooldown_ms=5_000, whitelisted=False).allowed is True


def test_whitelisted_client_bypasses_window():
    assert evaluate(now_ms=4_000, stored_next_ms=6_000, cooldown_ms=5_000, whitelisted=True).allowed is True
