# Receipt Processing Contract

## Single-image policy

An order accepts one receipt image per submission attempt. Additional images sent while an attempt is being processed are not treated as additional evidence for that attempt.

Supported MIME types are JPEG, PNG, and WEBP. PDF processing is outside the MVP.

## Attempt policy

Each order has at most three receipt submission attempts. Attempts are strictly sequential: `1 -> 2 -> 3`.

A failed attempt records its processing and verification reason. After the third failed attempt, the order enters administrative escalation and the user is no longer offered another receipt attempt.

## Concurrency invariant

Attempt allocation is serialized per `internal_order_id` at the database level using a transaction-scoped PostgreSQL advisory lock. This prevents concurrent submissions from observing the same attempt count and claiming the same attempt number.

The database also enforces the maximum of three attempts and sequential numbering through the `receipt_submissions_attempt_limit` trigger.
