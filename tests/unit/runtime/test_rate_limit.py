from app.runtime.telegram.rate_limit import TelegramRateLimiter


class Clock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def test_general_bucket_allows_configured_burst_then_rejects() -> None:
    clock = Clock()
    limiter = TelegramRateLimiter(clock=clock)

    decisions = [limiter.check(101, "general") for _ in range(9)]

    assert all(decision.allowed for decision in decisions[:8])
    assert decisions[8].allowed is False
    assert decisions[8].retry_after > 0


def test_financial_bucket_is_stricter_than_general_bucket() -> None:
    clock = Clock()
    limiter = TelegramRateLimiter(clock=clock)

    decisions = [limiter.check(202, "financial") for _ in range(4)]

    assert all(decision.allowed for decision in decisions[:3])
    assert decisions[3].allowed is False


def test_upload_bucket_allows_only_one_burst() -> None:
    clock = Clock()
    limiter = TelegramRateLimiter(clock=clock)

    first = limiter.check(303, "upload")
    second = limiter.check(303, "upload")

    assert first.allowed is True
    assert second.allowed is False


def test_repeated_abuse_escalates_to_temporary_cooldown() -> None:
    clock = Clock()
    limiter = TelegramRateLimiter(clock=clock)

    for _ in range(3):
        limiter.check(404, "upload")
    denied = limiter.check(404, "upload")

    assert denied.allowed is False
    assert denied.retry_after >= 30


def test_rate_limit_state_isolated_between_users() -> None:
    clock = Clock()
    limiter = TelegramRateLimiter(clock=clock)

    for _ in range(8):
        assert limiter.check(505, "general").allowed

    assert limiter.check(505, "general").allowed is False
    assert limiter.check(506, "general").allowed is True


def test_tokens_refill_after_time_passes() -> None:
    clock = Clock()
    limiter = TelegramRateLimiter(clock=clock)

    for _ in range(8):
        assert limiter.check(606, "general").allowed

    assert limiter.check(606, "general").allowed is False
    clock.advance(2.0)
    assert limiter.check(606, "general").allowed is True
