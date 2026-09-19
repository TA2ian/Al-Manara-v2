# ADR-002: Receipt Linkage and Verification

## Status

Accepted.

## Decision

The MVP accepts receipt evidence as image files only: JPEG, PNG, and WEBP. PDF is explicitly outside the MVP processing boundary.

If a customer has a ShamCash receipt as a PDF, the bot asks the customer to open the PDF and send a clear screenshot of the receipt page as a supported image. The backend does not receive, parse, render, or process the original PDF.

Customer receipt submission does not accept a transaction-reference text message. The legacy transaction-reference fields remain only for compatibility with historical data and contracts; they are not required or used as customer verification input.

Receipt processing, when automated extraction is enabled, applies only to customer-submitted images. The admin does not upload or submit a second receipt to the bot. Instead, the admin reviews the customer-submitted receipt and the order's persisted financial data manually, then makes the explicit approval/rejection decision through the existing admin review flow.

The source of a customer file is recorded as `receipt_source=customer`. The legacy `admin_verified` enum value is retained only for historical schema compatibility and is not a supported MVP submission path.

### Blocking linkage rule

`public_order_code` is the mandatory blocking linkage field for automated customer-receipt linkage.

If it is missing or does not identify the current order, the automated customer-receipt path must not link it to that order. The admin review screen may still display the submitted receipt and its extracted/available evidence for manual inspection; the admin can resolve the case through the existing review decision flow.

### Non-blocking comparison fields

Sender name, sender account, recipient name, recipient account, amount, currency, operation type, date, extraction confidence, and any transaction reference visible on the image produce explicit field-level results and warnings. A transaction reference is evidence only; it is not supplied by the customer as a text field and is not a blocking customer-side verification requirement.

### Duplicate operation number

A successfully linked `shamcash_operation_number` cannot be successfully reused for another order. This rule applies only when an operation number is independently established from trusted review evidence; a customer-provided text value cannot establish or satisfy this condition.

### Image security

Image handling is isolated and resource-bounded. Files are limited to 5 MB, validated by actual file content rather than filename/declared MIME type, safely decoded with dimension/memory limits, normalized/re-encoded, and stripped of unnecessary metadata before storage.

OCR/QR processing produces data only. It has no direct authority to modify orders, settings, or audit records.

## Consequences

- The customer receipt path is image-only; the admin does not upload a separate receipt.
- PDF parser dependencies and PDF attack surface are excluded from the MVP.
- Customer-supplied transaction-reference text cannot create circular self-verification.
- An unrelated or old receipt cannot be force-linked automatically.
- Automated extraction, when enabled, remains evidence and review assistance, never financial authorization.
- The admin reviews the order and customer receipt manually and retains explicit control over approval/rejection.

## Rejected alternatives

### PDF processing in MVP

Rejected because the current MVP contract explicitly limits receipt evidence to JPEG/PNG/WEBP. Adding PDF parsing now would expand the attack surface and implementation scope without being required for launch.

### Customer transaction-reference text as verification input

Rejected because it is self-asserted data and can become circular if the same value is persisted as the expected reference. The MVP instead derives verification evidence from the submitted image and keeps transaction references, when visible on an image, as non-blocking evidence.

### Separate customer/admin verification algorithms

Rejected because `receipt_source` is provenance metadata, not a business-rule switch.

### Admin-uploaded receipt evidence

Rejected because the admin can inspect the customer's submitted receipt together with the persisted order and financial snapshot directly. A second admin-uploaded evidence path would duplicate evidence handling, complicate provenance/attempt semantics, and add unnecessary attack surface without improving the manual review decision.
