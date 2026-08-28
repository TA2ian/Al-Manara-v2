# Al-Manara v2 Domain Model

## Core aggregates

### User

Owns the customer identity and customer payment identity.

```text
User
├── CustomerPaymentIdentity
├── Wallets
├── Orders
└── VerificationRequests
```

`CustomerPaymentIdentity` contains the verified ShamCash sender name and sender account used as the comparison baseline for later receipts.

### Wallet

Represents a customer's USDT destination wallet.

State:

```text
PENDING -> VERIFIED
PENDING -> REJECTED
VERIFIED -> DISABLED
```

Wallet registration accepts text address, QR, or wallet-share input. The wallet stores normalized destination data and explicit network identity.

### Order

The purchase aggregate contains:

```text
internal_order_id
public_order_code
user_id
wallet_id
network_code
status
version
financial_snapshot
payment_snapshot
receipt_source
created_at
updated_at
```

The aggregate does not contain Telegram message state.

### OrderFinancials

```text
requested_amount
fee_percent
fee_amount
net_usdt_amount
payment_currency
exchange_rate
local_amount
rounding_policy
```

All values are `Decimal` where monetary precision matters.

### PaymentSnapshot

The order records the recipient ShamCash identity used when the order was created:

```text
recipient_shamcash_account
recipient_name
payment_method
```

Changing the administrator's current payment account does not mutate historical orders.

### ReceiptData

```text
operation_type
operation_number
operation_date
sender_name
sender_account
recipient_name
recipient_account
amount
currency
note
fingerprint_text
extraction_confidence
warnings
```

`operation_number` is the domain representation of `shamcash_operation_number` and must never be exposed through blockchain terminology.

### ReceiptVerificationResult

```text
is_linked_to_order
comparison_status
field_results
warnings
```

`is_linked_to_order=false` prevents review linkage. Comparison warnings are advisory and do not make an automatic decision.

### NetworkConfig

Network behavior is data-driven and includes enablement, format validation, memo requirements, fee, limits, and presentation metadata.

## Domain services

The first planned authoritative services are:

- `OrderTransitionService`
- `WalletRegistrationService`
- `WalletVerificationService`
- `ReceiptVerificationService`
- `PricingService`
- `ExchangeService`
- `AuthorizationService`
- `SettingsService`
- `NotificationService`

These services own business rules. Telegram handlers orchestrate commands and render results only.

## Exceptions

The domain/application error taxonomy includes:

- `ValidationError`
- `NotFoundError`
- `ConflictError`
- `UnauthorizedError`
- `ForbiddenError`
- `InvalidTransitionError`
- `PaymentError`
- `WalletValidationError`
- `ExchangeRateUnavailableError`

Infrastructure-specific exceptions are translated at the application boundary rather than leaking into Telegram handlers.
