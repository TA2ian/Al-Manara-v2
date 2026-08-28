# Database Layer

The initial PostgreSQL persistence contract is defined in `db/migrations/0001_initial_schema.sql`.

## Current policy

- PostgreSQL is the authoritative persistence layer for business state.
- `orders.status` is the authoritative order lifecycle state.
- `orders.version` supports optimistic concurrency.
- Order financial terms are immutable in `order_financial_snapshots`.
- Durable receipt evidence is represented by opaque object-storage metadata in PostgreSQL; binary receipt files are not stored in PostgreSQL.
- Only BEP20 and TRC20 are enabled at launch.
- ShamCash operation references use `shamcash_operation_number` and are never represented as blockchain transaction identifiers.
- `public_order_code` is separate from `internal_order_id`.
- Audit logs are append-only.

This migration is the schema contract. Application repositories and services must enforce the same invariants rather than creating alternate state paths.
