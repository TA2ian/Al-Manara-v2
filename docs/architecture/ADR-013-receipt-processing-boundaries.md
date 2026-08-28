# ADR-013: Receipt Processing Boundaries

## Status

Accepted.

## MVP receipt formats

Only these receipt image formats are supported:

- JPEG
- PNG
- WEBP

PDF processing is explicitly out of MVP. The backend does not parse, render, OCR, inspect, or otherwise process PDF receipt files.

If the customer has a PDF receipt, the user flow instructs the customer to open the file and send a clear screenshot/image of the receipt.

## Processing boundary

Receipt files are untrusted input and must pass through the following boundary before business comparison:

```text
Telegram file
    ↓
streaming size limit (5 MB)
    ↓
magic-byte / real MIME validation
    ↓
safe image decode with dimension/memory limits
    ↓
metadata removal / safe re-encoding
    ↓
isolated OCR worker
    ↓
ReceiptData
    ↓
ReceiptVerificationService
    ↓
Application Service
```

The decoder/OCR worker must not write directly to Orders, Settings, or other business tables.

## Isolation

Image decoding and OCR execute outside the Telegram request handler and in a bounded worker/process environment with:

- execution timeout
- bounded memory
- bounded image dimensions
- bounded processing queue
- bounded retry count
- no shell execution from user-controlled input
- no dynamic import or code execution from uploaded files

Processing failures are classified and returned to the application as explicit outcomes.

## Receipt attempt policy

The one-image-per-attempt and maximum-three-attempt policy is authoritative in `ADR-011`.

Only one receipt-processing job may be active for an order at a time. Additional image submissions while the active job is processing must not create parallel OCR jobs for that order.

## Comparison boundary

OCR output is data, not instructions. It is normalized into the domain `ReceiptData` structure and then evaluated by the single `ReceiptVerificationService`.

Receipt source (`customer` or `admin_verified`) may be recorded for audit purposes but must not select a different comparison algorithm.

## Security

The system must never trust:

- Telegram-reported MIME type
- filename extension
- filename content
- OCR text as executable instructions
- image metadata

Stored files use generated opaque identifiers rather than original user-provided filenames and are placed in non-executable object storage.
