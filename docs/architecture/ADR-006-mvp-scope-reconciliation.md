# ADR-006: MVP Scope Reconciliation

## Status

Accepted.

## Purpose

This ADR records the reconciliation between the earlier architecture notes and the revised Master Engineering Contract (v2). It prevents obsolete requirements from silently re-entering implementation.

## Binding MVP decisions

### Receipt evidence

MVP receipt evidence is image-only:

- JPEG
- PNG
- WEBP

PDF processing is out of scope. A customer holding a PDF is instructed to open it and send a clear screenshot as an image. The backend processes only the resulting image.

### Admin step-up

TOTP is the mandatory primary step-up factor for sensitive administrator operations in the MVP. A second Telegram button alone is insufficient.

### Financial model

`OrderFinancials` explicitly contains `total_amount_user_pays`, which is equal to `local_amount` and never includes the USDT service fee as an added customer charge.

### Payment model

`PaymentMethod` is an explicit entity/configuration record, while each Order stores an immutable payment snapshot sufficient to reconstruct the recipient ShamCash details used at quote/payment time.

### Customer payment identity

`CustomerPaymentIdentity` is a first-class concept with explicit verification status and is the comparison baseline for future ShamCash receipts.

### Receipt source

`receipt_source` records provenance only. It never chooses a different verification algorithm.

### Legacy isolation

No runtime code is imported from the legacy repository. Migration is a separate data-only bridge.

## Explicitly excluded from MVP

- PDF parser/extractor/renderer
- PDF-specific worker pipeline
- Blockchain payment verification
- Automatic order approval
- Customer USDT selling/reverse-direction flows
- TON/ARB/ETH/SOL user-facing network selection

## Superseded notes

Any earlier architecture document that describes PDF processing as an MVP requirement is superseded by this ADR.

Any earlier security note that leaves the sensitive-action step-up factor unspecified is superseded by the TOTP decision recorded here.

## Implementation gate

No implementation may introduce an excluded capability without a new ADR that explicitly changes the MVP scope and identifies the affected tests, security boundary, and user-facing flows.
