# ADR-002: Receipt Linkage and Verification

## Status

Accepted.

## Decision

The MVP accepts receipt evidence as image files only: JPEG, PNG, and WEBP. PDF is explicitly outside the MVP processing boundary.

If a customer has a ShamCash receipt as a PDF, the bot asks the customer to open the PDF and send a clear screenshot of the receipt page as a supported image. The backend does not receive, parse, render, or process the original PDF.

Receipt processing is split into extraction and comparison boundaries:

```text
Customer image ─┐
                ├─> Safe image processing/OCR ─> ReceiptData ─> ReceiptVerificationService
Admin image ────┘
```

The source of the file is recorded as `receipt_source` only. It must not select a different comparison algorithm.

### Blocking linkage rule

`public_order_code` is the mandatory blocking linkage field.

If it is missing or does not identify the current order, the receipt cannot enter `UNDER_REVIEW` for that order.

For customer-submitted evidence, the customer is asked to resend a correctly linked receipt image. For admin-submitted evidence, the admin is shown the linkage failure and must provide the correct evidence/order context.

### Non-blocking comparison fields

Sender name, sender account, recipient name, recipient account, amount, currency, operation type, date, and extraction confidence produce explicit field-level results and warnings. They do not automatically approve or reject the order.

### Duplicate operation number

A successfully linked `shamcash_operation_number` cannot be successfully reused for another order.

### Image security

Image handling is isolated and resource-bounded. Files are limited to 5 MB, validated by actual file content rather than filename/declared MIME type, safely decoded with dimension/memory limits, normalized/re-encoded, and stripped of unnecessary metadata before storage.

OCR/QR processing produces data only. It has no direct authority to modify orders, settings, or audit records.

## Consequences

- Customer and admin receipt paths share exactly one comparison service.
- PDF parser dependencies and PDF attack surface are excluded from the MVP.
- A customer with a PDF has an explicit, supported screenshot recovery path.
- An unrelated or old receipt cannot be force-linked to an order.
- Automated extraction remains evidence and review assistance, never financial authorization.

## Rejected alternatives

### PDF processing in MVP

Rejected because the current MVP contract explicitly limits receipt evidence to JPEG/PNG/WEBP. Adding PDF parsing now would expand the attack surface and implementation scope without being required for launch.

### Separate customer/admin verification algorithms

Rejected because `receipt_source` is provenance metadata, not a business-rule switch.
