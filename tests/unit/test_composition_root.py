from __future__ import annotations

from app.composition_root import AdminComposition, build_admin_composition


class DummyClient:
    pass


class DummyUnitOfWork:
    pass


def test_build_admin_composition_wires_all_admin_handlers() -> None:
    composition = build_admin_composition(DummyClient(), DummyUnitOfWork())  # type: ignore[arg-type]

    assert isinstance(composition, AdminComposition)
    assert composition.review.__class__.__name__ == "TelegramAdminReviewHandler"
    assert composition.listing.__class__.__name__ == "TelegramAdminOrderListingHandler"
    assert composition.closure.__class__.__name__ == "TelegramAdminOrderClosureHandler"
    assert composition.session.__class__.__name__ == "TelegramAdminSessionHandler"
    assert composition.fulfillment.__class__.__name__ == "TelegramFulfillmentHandler"
