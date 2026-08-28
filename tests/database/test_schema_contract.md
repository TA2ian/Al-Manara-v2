# Database Schema Verification Contract

The database test suite must verify at minimum:

1. Only `BEP20` and `TRC20` are enabled at launch.
2. `TON`, `ARB`, `ETH`, and `SOL` are disabled and therefore absent from user selection queries.
3. `public_order_code` is unique and distinct from `internal_order_id`.
4. `shamcash_operation_number` cannot be duplicated.
5. Financial snapshots cannot be updated or deleted.
6. Financial invariants enforce deduction semantics: `net_usdt_amount = requested_amount - fee_amount` and never an added fee in `local_amount`.
7. `NEW.SYP` requires a positive exchange rate; `USD` does not.
8. Receipt evidence accepts only JPEG/PNG/WEBP and rejects objects over 5 MiB at the database contract boundary.
9. Audit records cannot be updated or deleted.
10. Historical records cannot be destructively removed through customer deletion.
11. Order status mutation requires a version increment, supporting the application-level authoritative transition service.

These checks are complements to application unit/integration tests; they are not substitutes for testing the actual repository and service implementations.
