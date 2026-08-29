from __future__ import annotations

from typing import Protocol

from app.application.ports import IdempotencyRepository, OrderRepository


class Transaction(Protocol):
    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


class UnitOfWork(Protocol):
    orders: OrderRepository
    idempotency: IdempotencyRepository

    async def __aenter__(self) -> UnitOfWork: ...

    async def __aexit__(self, exc_type: object, exc_value: object, traceback: object) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...
