# Contract Gates

The implementation must not advance to application orchestration until the persistence contract is deterministic and concurrency-safe.

## Gate: receipt submission allocation

- Maximum attempts: 3 per order.
- Attempt numbers: strictly sequential starting at 1.
- Allocation is serialized per `internal_order_id` in PostgreSQL with a transaction-scoped advisory lock.
- A fourth attempt is rejected at the database boundary.
- An idempotency key replay returns the existing submission instead of allocating a new attempt.
- A duplicate idempotency key cannot be rebound to a different order.
- Only one receipt submission for an order may be `PROCESSING` at a time.
- A failed third attempt escalates to the administrator and closes further customer attempts.
- Each failed attempt retains its reason for user feedback and auditability.

This gate is closed only when the migration and database contract tests verify the atomic reservation and finalization functions, per-order serialization, attempt limit, processing uniqueness, and idempotent replay behavior.
