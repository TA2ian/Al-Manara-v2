# Verified Current Al-Manara Behavior Inventory

This inventory is intentionally limited to behavior confirmed from the current repository inspection and the already-established migration decisions.

## Wallets

- User wallet registration requires selecting a supported network first.
- Wallet input can be an address, QR image, or wallet-app shared payload.
- QR data is decoded and normalized; when an address is supplied with the QR, the two values must match before acceptance.
- Wallets shown to users are restricted to verified, non-deleted entries with QR evidence.
- Verified wallets are treated as immutable; changing address/network/QR/verification requires replacement rather than mutation.
- A wallet linked to an active order is protected from deletion.

## Payment/order data

- Orders retain payment and financial snapshots rather than depending on mutable current configuration after creation.
- USD does not use an exchange-rate conversion; NEW.SYP uses the captured exchange-rate snapshot.
- Payment-method/account data is snapshotted for the order.
- Current Al-Manara contains database-level order-state constraints and active-order guards.
- Current Al-Manara contains administrative closure/session-ownership hardening and regression coverage; these must be reimplemented in v2 after their exact handlers/contract paths are mapped.

## Receipt input

- PDF is format-detected and routed to user guidance in the current MVP path; PDF parsing/rendering/OCR is not part of that path.
- Image processing is constrained by MIME/content validation and image safety limits.
- Receipt processing uses bounded attempts and concurrency/idempotency protections.

## Explicit migration decisions

- Do not restore the removed first TON rule or functionality coupled only to it.
- Do not add a TXID single-use prohibition.
- Do not make activation depend on geography or local timezone/clock; duration/expiry is authoritative.
- Preserve behavior, not legacy implementation structure.
