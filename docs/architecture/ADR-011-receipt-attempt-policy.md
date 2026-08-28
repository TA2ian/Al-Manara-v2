# ADR-011: Receipt Submission Attempt Policy

## Status

Accepted.

## Decision

A customer may submit **one receipt image per verification attempt** for an order.

The maximum number of receipt verification attempts for a single order is:

```text
3
```

An attempt consists of exactly one JPEG, PNG, or WEBP image submitted for receipt verification.

Multiple images sent while an attempt is being processed are not processed as a batch. The active attempt is processed first; additional submissions are rejected while processing is in progress and do not create parallel OCR work for the same order.

## Attempt flow

```text
Attempt 1
    ↓
validation → extraction → verification
    ↓ failure
clear failure reason to customer
    ↓
Attempt 2
    ↓ failure
clear failure reason to customer
    ↓
Attempt 3 (final)
    ↓ failure
escalate to administrator manual review
```

There is no fourth automatic customer attempt.

## Failure handling

A retryable failure must provide the customer with the specific reason and the corrective action where possible.

Examples include:

- image unreadable → request a clearer image
- required receipt information cannot be extracted → request a clearer/full receipt image
- `public_order_code` missing or mismatched → request a new receipt image showing the correct order code in the ShamCash note

Field mismatches that are explicitly non-blocking under the Receipt Verification contract (for example sender-name or amount mismatch when the evidence is otherwise readable and correctly linked) must not be incorrectly treated as an image-processing failure merely to force a retry. They remain warnings for manual administrator review.

Security validation failures, including oversized or invalid-format files, are recorded as rejected submissions and contribute to the applicable anti-abuse/rate-limit policy. They must not trigger unbounded retries.

## Final-attempt escalation

When the third attempt fails verification, the system stops requesting automatic replacement images and creates/escalates the evidence for administrator manual review.

The administrator view must contain, where available:

- the order and customer context
- all submitted receipt evidence for the attempts
- attempt number and timestamp
- failure reason for each attempt
- extracted `ReceiptData`
- `ReceiptVerificationResult`
- `shamcash_operation_number` when extracted
- expected `local_amount` and currency
- customer `CustomerPaymentIdentity`
- `public_order_code`

Escalation does not itself transition the order to `UNDER_REVIEW` unless the authoritative application flow determines that the receipt is sufficiently linked according to the existing order-state contract. A failed or unlinked receipt must not bypass the `public_order_code` linkage requirement.

## Concurrency and idempotency

Only one receipt-processing job may be active for an order at a time.

Duplicate Telegram deliveries and repeated callbacks must not create duplicate attempts or duplicate OCR jobs.

The attempt count is persistent application data, not FSM state and not an in-memory counter.

## Relationship to existing limits

This per-order limit is separate from the global anti-abuse limit for file uploads per user/hour. Both apply:

- maximum 3 verification attempts per order
- maximum 10 receipt/image uploads per user per hour by default

The global limit protects infrastructure; the per-order limit controls the business flow.

## Security and architecture invariants

- One image per attempt.
- No parallel receipt processing for the same order.
- No automatic approval after any attempt.
- `public_order_code` remains the blocking linkage check.
- OCR/extraction remains isolated from persistence and order-state mutation.
- `ReceiptVerificationService` remains the single comparison service regardless of receipt source.
- Failed attempts do not reset or corrupt the Order FSM/application interaction state.
