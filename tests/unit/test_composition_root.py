from __future__ import annotations

from typing import Any

from app.composition_root import AdminComposition, build_admin_composition


class DummyClient:
    def rpc(self, function_name: str, params: dict[str, Any]):
        raise AssertionError(f"RPC must not execute during composition: {function_name}")


class DummyUnitOfWork:
    orders = object()
    idempotency = object()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        return None

    async def commit(self):
        return None

    async def rollback(self):
        return None


def test_build_admin_composition_wires_all_admin_handlers() -> None:
    composition = build_admin_composition(DummyClient(), DummyUnitOfWork())

    assert isinstance(composition, AdminComposition)
    assert composition.review.__class__.__name__ == "TelegramAdminOrderReviewHandler"
    assert composition.listing.__class__.__name__ == "TelegramAdminOrderListingHandler"
    assert composition.closure.__class__.__name__ == "TelegramAdminOrderClosureHandler"
    assert composition.session.__class__.__name__ == "TelegramAdminSessionHandler"
    assert composition.fulfillment.__class__.__name__ == "TelegramFulfillmentHandler"


def test_composition_does_not_execute_infrastructure_during_build() -> None:
    # A client that raises on every RPC proves construction is pure dependency wiring.
    composition = build_admin_composition(DummyClient(), DummyUnitOfWork())
    assert composition.review is not None
