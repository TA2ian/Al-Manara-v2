# ADR-019: Initial Database Schema

## Status

Accepted.

## Decision

The first persistence implementation uses PostgreSQL with explicit relational constraints for the domain contract defined by ADR-018.

`orders` owns lifecycle state and optimistic concurrency. Immutable quoted financial terms are stored in the one-to-one `order_financial_snapshots` table so they cannot be silently changed when operational order fields change.

Receipt binaries remain outside PostgreSQL. `receipt_evidence` stores only validated metadata and an opaque object-storage key. `receipt_submissions` represents individual one-image MVP attempts, allowing the three-attempt policy to be implemented at the application layer without conflating attempts with order state.

## Launch constraints

- `BEP20` and `TRC20` are enabled.
- `TON`, `ARB`, `ETH`, and `SOL` are present only as disabled configuration records.
- `USD` and `NEW.SYP` are the only payment currencies.
- `ROUND_HALF_UP` is the rounding policy.
- USD precision is 0.01.
- NEW.SYP precision is 0.01.
- USDT precision is 0.001.
- Rate precision is 0.001.
- Absolute receipt amount tolerance is 0.04.
- Admin backup mode is `EMERGENCY_ONLY`.
- PDF processing is outside MVP; receipt evidence accepts JPEG, PNG, and WEBP.

## Important boundary

The database schema does not make Telegram handlers authoritative. Application services remain responsible for legal Order transitions, authorization, TOTP step-up, idempotency, and notification coordination. Database constraints provide defense in depth and prevent invalid persistence, but they do not replace the domain transition service.
