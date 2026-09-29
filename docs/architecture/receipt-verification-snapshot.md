# Receipt verification snapshot contract

The receipt verification engine must never receive payment amounts or exchange-rate inputs directly from Telegram/admin text.

For every receipt verification, the authoritative financial source is `order_financial_snapshots`, joined to the immutable order identity fields required by the verification context.

## Mapping

- `payment_currency` <- `order_financial_snapshots.payment_currency`
- `expected_payment_amount` <- `order_financial_snapshots.local_amount`
- `exchange_rate` <- `order_financial_snapshots.exchange_rate`
- `fee_percent` <- `order_financial_snapshots.fee_percent`
- `rounding_policy_version` <- `order_financial_snapshots.rounding_policy_version`
- `network_code` <- `orders.network_code`
- `wallet_address` <- the order's wallet snapshot/verified wallet address used by the order
- `expected_reference` <- the authoritative Sham Cash operation/reference value when the workflow has one; otherwise `None`
- `tolerance` <- the persisted verification tolerance/settings value

`local_amount` is therefore the amount against which a Sham Cash receipt is financially compared. No second financial calculation is introduced.

Admin-uploaded evidence uses the same context and the same verification engine as customer-uploaded evidence. The source of the image changes provenance only; it does not change financial rules.

The OCR provider remains behind `OcrPort`. Selecting a production OCR vendor is intentionally outside this contract.
