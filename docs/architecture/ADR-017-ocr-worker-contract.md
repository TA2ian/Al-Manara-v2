# ADR-017: OCR Worker Contract

## Status

Accepted.

## Responsibility

The OCR worker is an isolated infrastructure component responsible only for converting an already validated receipt image into extraction data. It does not decide order state, approve payments, or write business state directly.

## Input

A job contains an opaque reference to a validated receipt image and immutable processing metadata required for the job.

The worker must not accept arbitrary shell commands, executable paths, dynamic Python module names, templates, SQL, or other user-selected execution parameters.

## Output

The worker returns structured extraction data sufficient for the application layer to construct `ReceiptData`, including extracted fields, confidence, warnings, and processing diagnostics that are safe to persist.

OCR output is untrusted data and must pass domain/application validation before comparison.

## Execution limits

Each job is bounded by:

- maximum image size: 5 MB
- configured maximum image dimensions
- configured memory limit
- configured execution timeout
- bounded retry count with backoff
- bounded queue capacity

A timeout or resource-limit failure produces a terminal classified failure for that attempt; it must not create an infinite retry loop.

## Isolation

The worker runs with the minimum permissions required to read the specific temporary input and write its result to the approved job/result channel.

It must not have direct database write access to Orders, Settings, Wallets, or Audit Logs.

It must not have access to production secrets unrelated to image processing.

## Concurrency

Only one active receipt-processing job is permitted for a given order at a time. Global concurrency is bounded so one user's uploads cannot consume all processing capacity.

The queue must be shared when multiple application processes are deployed.

## Lifecycle

```text
validated upload
    ↓
create idempotent processing job
    ↓
bounded queue
    ↓
isolated worker
    ↓
structured extraction result
    ↓
Application validation
    ↓
ReceiptVerificationService
```

The worker never transitions an Order and never performs automatic approval.
