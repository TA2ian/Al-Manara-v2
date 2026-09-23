from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID, uuid4

from app.application.order_creation_ports import (
    CustomerRepository,
    NetworkOrderRepository,
    OrderCreationRepository,
    PaymentSettingsRepository,
    PublicOrderCodeGenerator,
    WalletOrderRepository,
)
from app.application.quote import PurchaseQuote
from app.application.quote_ports import ExchangeRateProvider, FeePolicyProvider, QuoteClock
from app.domain.money import OrderFinancials
from app.domain.order_draft import PurchaseOrderDraft
from app.domain.payment_identity import AdminPaymentAccountSnapshot
from app.domain.wallet_selection import validate_wallet_for_order


@dataclass(frozen=True, slots=True)
class CreatePurchaseOrderCommand:
    user_id: int
    wallet_id: UUID
    network_code: str
    requested_amount: Decimal
    payment_currency: str


class CreatePurchaseOrderService:
    def __init__(
        self,
        customers: CustomerRepository,
        wallets: WalletOrderRepository,
        networks: NetworkOrderRepository,
        payments: PaymentSettingsRepository,
        orders: OrderCreationRepository,
        public_codes: PublicOrderCodeGenerator,
        exchange_rates: ExchangeRateProvider,
        fee_policies: FeePolicyProvider,
        clock: QuoteClock,
    ) -> None:
        self._customers = customers
        self._wallets = wallets
        self._networks = networks
        self._payments = payments
        self._orders = orders
        self._public_codes = public_codes
        self._exchange_rates = exchange_rates
        self._fee_policies = fee_policies
        self._clock = clock

    async def create(self, command: CreatePurchaseOrderCommand) -> object:
        now = self._clock.now()
        if now.tzinfo is None:
            raise RuntimeError("application clock must return a timezone-aware datetime")

        identity = await self._customers.get_payment_identity(command.user_id)
        if identity is None:
            raise ValueError("customer payment identity is not verified")

        wallet = await self._wallets.get_verified_for_user(command.wallet_id, command.user_id)
        if wallet is None:
            raise LookupError("verified wallet not found for customer")

        network = await self._networks.get_enabled(command.network_code)
        if network is None or not network.enabled:
            raise ValueError("selected network is unavailable")

        validate_wallet_for_order(wallet, command.user_id, network, command.requested_amount)

        payment_account = await self._payments.get_admin_payment_account()
        if payment_account is None:
            raise RuntimeError("admin payment account is not configured")

        fee_policy = await self._fee_policies.get_current_policy(network.code.value, now)
        if fee_policy is None:
            raise RuntimeError("current fee policy is unavailable")

        rate_snapshot = None
        exchange_rate = None
        if command.payment_currency == "NEW.SYP":
            rate_snapshot = await self._exchange_rates.get_current_rate("NEW.SYP", now)
            if rate_snapshot is None:
                raise RuntimeError("current exchange rate is unavailable")
            exchange_rate = rate_snapshot.rate
        elif command.payment_currency != "USD":
            raise ValueError("unsupported payment currency")

        financials = OrderFinancials.calculate(
            requested_amount=command.requested_amount,
            fee_percent=fee_policy.percent,
            payment_currency=command.payment_currency,
            exchange_rate=exchange_rate,
            rounding_policy_version="ROUND_HALF_UP:USD=0.01,NEW.SYP=0.01,USDT=0.001,RATE=0.001",
        )

        quote = PurchaseQuote(
            financials=financials,
            exchange_rate_snapshot=rate_snapshot,
            fee_policy_snapshot=fee_policy,
            expires_at=now,
        )

        draft = PurchaseOrderDraft(
            internal_order_id=uuid4(),
            public_order_code=self._public_codes.generate(),
            user_id=command.user_id,
            wallet_id=wallet.wallet_id,
            network=network.code,
            wallet_address=wallet.address,
            customer_payment_identity=identity,
            admin_payment_account=AdminPaymentAccountSnapshot(
                account_name=payment_account.account_name,
                account_number=payment_account.account_number,
                qr_image_file_id=payment_account.qr_image_file_id,
            ),
            financials=quote.financials,
        )
        return await self._orders.create_order_atomically(draft)
