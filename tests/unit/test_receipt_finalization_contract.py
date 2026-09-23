from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

import pytest


@dataclass
class Attempt:
    status: str = "PROCESSING"
    reason: str | None = None


class Finalizer:
    TERMINAL = {"VERIFIED", "FAILED", "ESCALATED"}

    def __init__(self) -> None:
        self.attempts: dict[object, Attempt] = {}

    def create(self):
        attempt_id = uuid4()
        self.attempts[attempt_id] = Attempt()
        return attempt_id

    def finalize(self, attempt_id, status: str, reason: str | None = None) -> Attempt:
        attempt = self.attempts[attempt_id]
        if attempt.status in self.TERMINAL:
            if attempt.status != status or attempt.reason != reason:
                raise RuntimeError("attempt already finalized")
            return attempt
        if status not in self.TERMINAL:
            raise ValueError("final status must be terminal")
        attempt.status = status
        attempt.reason = reason
        return attempt


def test_finalization_is_idempotent_for_same_result() -> None:
    finalizer = Finalizer()
    attempt_id = finalizer.create()
    first = finalizer.finalize(attempt_id, "VERIFIED")
    second = finalizer.finalize(attempt_id, "VERIFIED")
    assert second is first
    assert first.status == "VERIFIED"


def test_conflicting_finalization_is_rejected() -> None:
    finalizer = Finalizer()
    attempt_id = finalizer.create()
    finalizer.finalize(attempt_id, "VERIFIED")
    with pytest.raises(RuntimeError, match="already finalized"):
        finalizer.finalize(attempt_id, "FAILED", "late worker")


def test_non_terminal_finalization_is_rejected() -> None:
    finalizer = Finalizer()
    attempt_id = finalizer.create()
    with pytest.raises(ValueError, match="terminal"):
        finalizer.finalize(attempt_id, "PROCESSING")
