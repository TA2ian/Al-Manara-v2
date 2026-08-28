# ADR-001: Order and Financial Invariants

## Status

Accepted.

## Decision

The new system models order lifecycle and financial values independently from Telegram FSM state.

### Order state

`Order.status` is authoritative. The transition graph is explicitly defined in `ARCHITECTURE.md`. All transitions require `expected_version` and are executed by one application service.

### Financial model

The customer purchases `requested_amount` USDT. The service fee is deducted from the USDT amount sent after approval.

```text
fee_amount       = requested_amount * fee_percent
net_usdt_amount  = requested_amount - fee_amount
local_amount     = requested_amount * exchange_rate   # NEW.SYP
local_amount     = requested_amount                    # USD
```

There is no valid calculation in which `fee_amount` is added to the customer's ShamCash payment amount.

### Order snapshot

At order creation, the system stores the financial and network policy values used for the quote. Later Settings changes do not mutate historical orders.

The snapshot includes the rounding policy identifier and the exact exchange-rate snapshot.

## Consequences

- Financial calculations are testable without Telegram.
- Old gross/total semantics cannot leak into the new Domain.
- Receipt verification compares the receipt amount against `local_amount`, not the USDT quantity.
- Historical orders remain deterministic after Settings changes.

## Rejected alternatives

### Reuse legacy order fields

Rejected because the legacy model mixes local payment amounts, USDT amounts, fees, and generic transaction identifiers.

### Store order lifecycle in FSM

Rejected because Telegram sessions are not durable business state and can be stale or concurrent.

### Automatic approval after receipt MATCH

Rejected. Receipt verification is evidence and linkage assistance; approval remains an explicit administrator decision.
