# Receipt Processing Contract

## Single-image policy

An order accepts one receipt image per submission attempt. Additional images sent while an attempt is being processed are not treated as additional evidence for that attempt.

Supported MIME types are JPEG, PNG, and WEBP. PDF processing is outside the MVP.

## Attempt policy

Each order has at most three receipt submission attempts. Attempts are strictly sequential: `1 -> 2 -> 3`.

A failed attempt records its processing and verification reason. After the third failed attempt, the order enters administrative escalation and the user is no longer offered another receipt attempt.

## Concurrency invariant

Attempt allocation is serialized per `internal_order_id` at the database level using a transaction-scoped PostgreSQL advisory lock inside `reserve_receipt_submission`. This prevents concurrent submissions from observing the same attempt count and claiming the same attempt number.

The database enforces the maximum of three attempts with the `receipt_submissions_attempt_positive` constraint and prevents multiple simultaneous `PROCESSING` submissions for one order with a partial unique index.

## Idempotency invariant

Every receipt submission carries an application-generated idempotency key. The database stores that key uniquely with the submission and returns `replayed = true` when the same key is submitted again for the same order.

A replay must return the existing attempt without re-running image inspection, OCR, verification, finalization, or escalation.

## Finalization invariant

`finalize_receipt_submission` accepts only terminal processing states: `SUCCEEDED`, `FAILED`, or `ESCALATED`. It locks the submission row, rejects finalization of a non-`PROCESSING` submission, and requires a failure reason for `FAILED` and `ESCALATED` states.

The finalization RPC returns the complete persisted attempt payload so the application layer does not need to reconstruct domain state from partial database data.
