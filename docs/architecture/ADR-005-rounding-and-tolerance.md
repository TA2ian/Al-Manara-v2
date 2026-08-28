# ADR-005: Financial Precision and Receipt Tolerance

## Status

Accepted.

## Decisions

### Financial precision

The system uses `Decimal` exclusively for financial calculations.

| Value | Precision | Quantization unit |
|---|---:|---:|
| USD `local_amount` | 0.01 | `0.01` |
| NEW.SYP `local_amount` | 0.01 | `0.01` |
| USDT | 0.001 | `0.001` |
| Exchange rate | 0.001 | `0.001` |

### Rounding

Customer-facing financial calculations use:

```text
ROUND_HALF_UP
```

The selected precision and rounding policy are part of the order financial snapshot so later Settings changes cannot reinterpret an existing order.

### Receipt amount tolerance

The receipt amount comparison uses an absolute tolerance of:

```text
0.04
```

The tolerance is currency-denominated and applies to the receipt amount versus the order's snapshotted `local_amount` in the same payment currency.

The tolerance does not authorize an automatic financial decision. A value inside the tolerance may be reported as a tolerance match/warning, while the overall order decision remains manual.

### Tolerance timing

Tolerance is evaluated against the already-quantized and snapshotted order amount:

```text
QUANTIZED_SNAPSHOT
```

The comparison flow is therefore:

```text
Raw calculation
    ↓
Currency quantization using ROUND_HALF_UP
    ↓
OrderFinancials.local_amount snapshot
    ↓
Receipt extraction
    ↓
Compare receipt amount against snapshotted local_amount
    ↓
Apply absolute tolerance = 0.04
```

## Important distinction

Precision and tolerance are separate concepts:

- Precision determines how the system represents and snapshots the expected amount.
- Tolerance determines the maximum accepted difference when comparing an extracted receipt amount with that snapshot.

OCR uncertainty must not be hidden by monetary tolerance. If the extracted amount is not reliable enough to compare, the receipt remains `INCONCLUSIVE` regardless of numerical proximity.

## Financial invariants

```text
fee_amount = requested_amount × fee_percent
net_usdt_amount = requested_amount - fee_amount
USD local_amount = requested_amount
NEW.SYP local_amount = requested_amount × exchange_rate
total_amount_user_pays = local_amount
```

The service fee is deducted from the USDT delivered after approval and is never added to the customer's ShamCash payment amount.
