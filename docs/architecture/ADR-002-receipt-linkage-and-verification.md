# ADR-002: Receipt Linkage and Verification

## Status

Accepted.

## Decision

Receipt processing is split into extraction and comparison boundaries.

```text
Customer PDF/Image ─┐
                    ├─> Extraction ─> ReceiptData ─> ReceiptVerificationService
Admin PDF/Image ────┘
```

The source of the file is recorded as `receipt_source` only. It must not select a different comparison algorithm.

### Blocking rule

`public_order_code` is the only mandatory blocking linkage field.

If it is missing or does not identify the current order, the receipt cannot enter `UNDER_REVIEW` for that order.

### Non-blocking comparison fields

Sender name, sender account, recipient name, recipient account, amount, currency, operation type, date, and extraction confidence produce explicit field-level results and warnings. They do not trigger automatic approval or rejection.

### Duplicate operation number

A successfully linked `shamcash_operation_number` cannot be reused for another successful order.

### PDF security

PDF handling is text/layout extraction only, first page only, bounded to 5 MB and processed in an isolated worker. The processing stack must not execute embedded PDF JavaScript or interactive content.

Images use isolated OCR and safe decoding with explicit resource limits.

## Consequences

- Customer and admin receipt paths cannot silently diverge.
- Receipt verification can be tested as a pure application/domain capability.
- An unrelated or old receipt cannot be force-linked to an order.
- Automated extraction remains advisory evidence rather than financial authorization.
