from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from time import monotonic
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message

GENERAL_RATE_PER_MINUTE = 30.0
GENERAL_BURST = 8
FINANCIAL_RATE_PER_MINUTE = 8.0
FINANCIAL_BURST = 3
UPLOAD_RATE_PER_MINUTE = 3.0
UPLOAD_BURST = 1
ADMIN_RATE_PER_MINUTE = 20.0
ADMIN_BURST = 5
FULFILLMENT_RATE_PER_MINUTE = 4.0
FULFILLMENT_BURST = 1
VIOLATION_WINDOW_SECONDS = 60.0
FIRST_ESCALATION_COOLDOWN_SECONDS = 30.0
SECOND_ESCALATION_COOLDOWN_SECONDS = 120.0
MAX_TRACKED_BUCKETS = 10000


@dataclass(frozen=True, slots=True)
class RateLimitPolicy:
    rate_per_minute: float
    burst: int


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    allowed: bool
    retry_after: float = 0.0


@dataclass(slots=True)
class _Bucket:
    tokens: float
    updated_at: float
    violations: deque[float]
    locked_until: float = 0.0


POLICIES = {
    "general": RateLimitPolicy(GENERAL_RATE_PER_MINUTE, GENERAL_BURST),
    "financial": RateLimitPolicy(FINANCIAL_RATE_PER_MINUTE, FINANCIAL_BURST),
    "upload": RateLimitPolicy(UPLOAD_RATE_PER_MINUTE, UPLOAD_BURST),
    "admin": RateLimitPolicy(ADMIN_RATE_PER_MINUTE, ADMIN_BURST),
    "fulfillment": RateLimitPolicy(FULFILLMENT_RATE_PER_MINUTE, FULFILLMENT_BURST),
}


def classify_update(event: Message | CallbackQuery) -> str:
    if isinstance(event, CallbackQuery):
        data = (event.data or "").strip()
        if data.startswith("admin:fulfillment:"):
            return "fulfillment"
        if data.startswith("admin:"):
            return "admin"
        if data.startswith(("purchase:", "wallet:", "orders:")):
            return "financial"
        return "general"

    if event.photo is not None or event.document is not None:
        return "upload"

    text = (event.text or "").strip()
    command = text.split(maxsplit=1)[0].lower() if text.startswith("/") else ""
    if command in {"/buy", "/purchase", "/wallet_add", "/wallets"}:
        return "financial"
    if len(text) == 64 and all(char in "0123456789abcdefABCDEF" for char in text):
        return "fulfillment"
    return "general"


class TelegramRateLimiter:
    """In-process token-bucket limiter with bounded abuse escalation.

    The Telegram runtime already enforces a single active poller, so the
    limiter is intentionally local to the active process. No database I/O is
    performed on the update path.
    """

    def __init__(self, *, clock: Callable[[], float] = monotonic) -> None:
        self._clock = clock
        self._buckets: dict[tuple[int, str], _Bucket] = {}

    def check(self, user_id: int, category: str) -> RateLimitDecision:
        if not isinstance(user_id, int) or user_id <= 0:
            return RateLimitDecision(False, 60.0)

        if category not in POLICIES:
            category = "general"

        now = self._clock()
        self._prune(now)
        general = self._consume((user_id, "general"), POLICIES["general"], now)
        if not general.allowed:
            return general
        if category == "general":
            return general
        return self._consume((user_id, category), POLICIES[category], now)

    def _consume(
        self,
        key: tuple[int, str],
        policy: RateLimitPolicy,
        now: float,
    ) -> RateLimitDecision:
        bucket = self._buckets.get(key)
        if bucket is None:
            bucket = _Bucket(
                tokens=float(policy.burst),
                updated_at=now,
                violations=deque(),
            )
            self._buckets[key] = bucket

        elapsed = max(0.0, now - bucket.updated_at)
        bucket.updated_at = now
        bucket.tokens = min(
            float(policy.burst),
            bucket.tokens + elapsed * policy.rate_per_minute / 60.0,
        )

        if now < bucket.locked_until:
            return RateLimitDecision(False, bucket.locked_until - now)

        if bucket.tokens >= 1.0:
            bucket.tokens -= 1.0
            return RateLimitDecision(True)

        bucket.violations.append(now)
        cutoff = now - VIOLATION_WINDOW_SECONDS
        while bucket.violations and bucket.violations[0] < cutoff:
            bucket.violations.popleft()

        count = len(bucket.violations)
        if count >= 6:
            bucket.locked_until = now + SECOND_ESCALATION_COOLDOWN_SECONDS
        elif count >= 3:
            bucket.locked_until = now + FIRST_ESCALATION_COOLDOWN_SECONDS

        retry = max(60.0 / policy.rate_per_minute, bucket.locked_until - now)
        return RateLimitDecision(False, retry)

    def _prune(self, now: float) -> None:
        if len(self._buckets) < MAX_TRACKED_BUCKETS:
            return
        stale = [
            key for key, bucket in self._buckets.items()
            if bucket.updated_at < now - VIOLATION_WINDOW_SECONDS
            and bucket.locked_until <= now
        ]
        for key in stale:
            self._buckets.pop(key, None)
        if len(self._buckets) >= MAX_TRACKED_BUCKETS:
            oldest = min(self._buckets, key=lambda key: self._buckets[key].updated_at)
            self._buckets.pop(oldest, None)

    def size(self) -> int:
        return len(self._buckets)


class TelegramRateLimitMiddleware(BaseMiddleware):
    """Rate-limit Telegram updates before any application handler executes."""

    def __init__(self, limiter: TelegramRateLimiter | None = None) -> None:
        self._limiter = limiter or TelegramRateLimiter()

    async def __call__(
        self,
        handler: Callable[[Any, dict[str, Any]], Awaitable[Any]],
        event: Any,
        data: dict[str, Any],
    ) -> Any:
        user = getattr(event, "from_user", None)
        user_id = getattr(user, "id", None)
        if not isinstance(user_id, int) or user_id <= 0:
            return await handler(event, data)

        decision = self._limiter.check(user_id, classify_update(event))
        if decision.allowed:
            return await handler(event, data)

        retry_seconds = max(1, int(decision.retry_after + 0.999))
        if isinstance(event, CallbackQuery):
            await event.answer(
                f"الطلبات متكررة جدًا. حاول بعد {retry_seconds} ثانية.",
                show_alert=True,
            )
        elif isinstance(event, Message):
            await event.answer(
                f"الطلبات متكررة جدًا. حاول بعد {retry_seconds} ثانية."
            )
        return None
