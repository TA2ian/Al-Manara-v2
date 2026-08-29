# Contract Gates

The implementation must not advance to application orchestration until the persistence contract is deterministic and concurrency-safe.

## Gate: receipt attempt allocation

- Maximum attempts: 3 per order.
- Attempt numbers: strictly sequential starting at 1.
- Allocation is serialized per order in PostgreSQL.
- A fourth attempt is rejected at the database boundary.
- A failed third attempt escalates to the administrator.
- Each failed attempt retains its reason for user feedback and auditability.

This gate is closed only when the migration and database contract tests verify the trigger and its per-order serialization mechanism.
