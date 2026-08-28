# ADR-005: Financial Precision and Receipt Tolerance

## Status

Open decision — implementation is blocked until the business values are approved.

## Required decisions

1. Decimal precision for `local_amount` in USD.
2. Decimal precision for `local_amount` in `NEW.SYP`.
3. Rounding mode.
4. Receipt amount tolerance, absolute and/or percentage.
5. Whether tolerance is evaluated before or after currency-specific quantization.

## Required invariants

The selected policy must be deterministic, stored with the order financial snapshot, and reused when interpreting that order's receipt.

No financial calculation may use binary floating point. Monetary values use `Decimal` with an explicit context and quantization policy.

## Technical recommendation (not yet a business decision)

A reasonable baseline for consideration is:

- USD: 2 decimal places.
- NEW.SYP: 2 decimal places unless the actual ShamCash operational amount requires a different precision.
- `ROUND_HALF_UP` for customer-facing quote quantization.
- Receipt tolerance represented explicitly as a policy object rather than a hard-coded percentage.

These values remain recommendations only and are **not accepted business values** until approved.

## Rationale

Rounding and tolerance affect the amount the customer is asked to pay and the interpretation of a ShamCash receipt. They are business rules, not implementation details, and cannot be silently inferred by code.
