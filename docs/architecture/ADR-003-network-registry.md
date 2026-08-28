# ADR-003: Data-Driven Network Registry

## Status

Accepted.

## Decision

Supported USDT destination networks are represented by configuration/domain records rather than Telegram handler branches.

Launch configuration enables only BEP20 and TRC20. TON, ARB, ETH, and SOL may exist as disabled records but must be invisible to customers while disabled.

Each network defines:

- `code`
- `display_name`
- `enabled`
- `address_regex`
- `address_validator`
- `requires_memo`
- `explorer_url_template`
- `service_fee_percent`
- `min_amount`
- `max_amount`
- `icon_or_emoji`

Network validation is isolated from order lifecycle and payment processing.

## Consequences

Adding a new network should require a network configuration entry and its format validator without modifying order, payment, or admin workflows.

TON is intentionally not treated as a normal address-only network because future activation requires explicit memo/tag support in the domain model.

No blockchain explorer is used to verify the customer's payment. Network data describes the destination address for the administrator's later manual USDT transfer.
