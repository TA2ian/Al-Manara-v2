from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

import pytest


@dataclass(frozen=True)
class Reservation:
    submission_id: object
    attempt_number: int


class InMemoryIdempotentReservation:
    def __init__(self) -> None:
        self._by_key: dict[str, Reservation] = {}
        self._next_attempt: dict[object, int] = {}

    def reserve(self, order_id: object, idempotency_key: str) -> Reservation:
        if not idempotency_key.strip():
            raise ValueError("idempotency_key cannot be blank")
        existing = self._by_key.get(idempotency_key)
        if existing is not None:
            return existing
        attempt = self._next_attempt.get(order_id, 0) + 1
        if attempt > 3:
            raise RuntimeError("receipt attempt limit exceeded")
        reservation = Reservation(uuid4(), attempt)
        self._by_key[idempotency_key] = reservation
        self._next_attempt[order_id] = attempt
        return reservation


def test_same_idempotency_key_reuses_submission() -> None:
    repository = InMemoryIdempotentReservation()
    order_id = uuid4()
    first = repository.reserve(order_id, "telegram:update:42")
    replay = repository.reserve(order_id, "telegram:update:42")
    assert replay == first
    assert replay.attempt_number == 1


def test_different_keys_allocate_sequential_attempts() -> None:
    repository = InMemoryIdempotentReservation()
    order_id = uuid4()
    first = repository.reserve(order_id, "update:1")
    second = repository.reserve(order_id, "update:2")
    third = repository.reserve(order_id, "update:3")
    assert (first.attempt_number, second.attempt_number, third.attempt_number) == (1, 2, 3)


def test_fourth_distinct_submission_is_rejected() -> None:
    repository = InMemoryIdempotentReservation()
    order_id = uuid4()
    for index in range(3):
        repository.reserve(order_id, f"update:{index}")
    with pytest.raises(RuntimeError, match="attempt limit exceeded"):
        repository.reserve(order_id, "update:4")


def test_blank_idempotency_key_is_rejected() -> None:
    repository = InMemoryIdempotentReservation()
    with pytest.raises(ValueError, match="idempotency_key"):
        repository.reserve(uuid4(), "   ")
