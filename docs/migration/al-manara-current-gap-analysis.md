# Al-Manara → v2 Migration Gap Analysis

## Purpose

This document defines the migration boundary between the current Al-Manara implementation and Al-Manara v2. Runtime behavior is rebuilt inside v2's domain/application/infrastructure architecture; legacy runtime modules are not copied wholesale.

## Verified v2 capabilities already established

- Atomic purchase-order creation with customer identity, verified-wallet, network, amount, payment-account, quote, financial snapshot and idempotency validation.
- Atomic order state transition with optimistic version checking and append-only audit logging.
- Immutable financial snapshots.
- Receipt submission reservation with per-order PostgreSQL advisory locking, sequential attempts, maximum three attempts, one PROCESSING submission per order, and idempotent replay.
- Receipt finalization restricted to terminal processing states and third-attempt escalation.
- Receipt image inspection for JPEG/PNG/WEBP with declared-type/content matching, byte, dimension and pixel limits.
- PDF is deliberately classified for user guidance rather than parsed in the MVP path.
- Receipt OCR/verification orchestration is isolated behind application/domain ports.
- USD and NEW.SYP financial snapshots and currency-aware admin payment account selection.
- Verified-wallet ownership/network/amount validation.

## Current Al-Manara behavior that must be preserved or reimplemented

1. Wallet registration and verification UX, including selected-network validation and QR/address matching.
2. Saved-wallet lifecycle and protection rules, including verified-wallet immutability and protection while linked to an active order.
3. Canonical payment-method setup/routing behavior and currency-specific payment account handling.
4. Order lifecycle and administrative closure behavior, including session ownership/context guards where present in the authoritative current implementation.
5. Customer/admin status messaging and canonical payment-confirmation UI behavior.
6. Receipt input matrix and media security behavior, including PDF guidance and supported image handling.
7. Receipt retry/concurrency behavior and user-facing escalation semantics.
8. Exchange-rate, fee, rounding and quote-expiry behavior.
9. Audit logging and administrative controls.
10. CI/regression tests that encode fixes already made in current Al-Manara.

## Explicit exclusions

- Do not reintroduce the removed first `TON` rule or functionality coupled exclusively to it.
- Do not introduce a rule that forbids reuse of TXIDs.
- Do not introduce timezone/geographic-location dependence for activation timing; duration/expiry semantics remain authoritative.
- Do not import legacy database migration code merely because it exists; reproduce only the required behavior through the v2 persistence contract.

## Migration rule

For every legacy capability: preserve externally observable behavior and security invariants, but implement it using v2's domain/application/infrastructure boundaries and authoritative database contracts. If a legacy behavior conflicts with an explicit current decision above, the explicit decision wins.
