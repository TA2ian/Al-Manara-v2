# ADR-005: Financial Precision and Receipt Tolerance

## Status

Proposed — implementation is blocked until explicit business values are selected.

## Open decisions

The following values must be approved before financial services are finalized:

1. Decimal precision for `local_amount` in USD.
2. Decimal precision for `local_amount` in `NEW.SYP`.
3. Rounding mode (`ROUND_HALF_UP`, `ROUND_UP`, or another explicitly selected policy).
4. Receipt amount tolerance, expressed as an absolute amount and/or percentage.
5. Whether tolerance applies before or after currency-specific quantization.

## Required invariant

The selected policy must be deterministic, persisted as part of the order financial snapshot, and reused by receipt comparison for that order.

No financial calculation may depend on Python binary floating point. Monetary values use `Decimal` with an explicit context and quantization policy.

## Rationale

Rounding and tolerance affect the amount the customer is asked to pay and the interpretation of a ShamCash receipt. They are business rules, not implementation details, and therefore cannot be silently inferred by the code.
