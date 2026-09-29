from uuid import UUID

from app.runtime.telegram.fulfillment import (
    fulfillment_action_markup,
    parse_fulfillment_callback,
)


def test_fulfillment_callback_is_version_bound() -> None:
    order_id = UUID("11111111-1111-1111-1111-111111111111")
    parsed = parse_fulfillment_callback(f"admin:fulfillment:claim:{order_id}:8")

    assert parsed == ("claim", order_id, 8)


def test_fulfillment_callback_rejects_unknown_operation() -> None:
    order_id = UUID("11111111-1111-1111-1111-111111111111")
    assert parse_fulfillment_callback(f"admin:fulfillment:approve:{order_id}:8") is None


def test_claim_markup_and_complete_markup_are_distinct() -> None:
    order_id = UUID("11111111-1111-1111-1111-111111111111")
    claim = fulfillment_action_markup(order_id, 8, claimed=False)
    complete = fulfillment_action_markup(order_id, 9, claimed=True)

    assert claim.inline_keyboard[0][0].text == "استلام للتنفيذ"
    assert claim.inline_keyboard[0][0].callback_data == f"admin:fulfillment:claim:{order_id}:8"
    assert complete.inline_keyboard[0][0].text == "إتمام التسليم"
    assert complete.inline_keyboard[0][0].callback_data == f"admin:fulfillment:complete:{order_id}:9"
