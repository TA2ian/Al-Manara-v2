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
    exchange_rate: Decimal | None
    rounding_policy_version: str


class CreatePurchaseOrderService:
    def __init__(
        self,
        customers: CustomerRepository,
        wallets: WalletOrderRepository,
        networks: NetworkOrderRepository,
        payments: PaymentSettingsRepository,
        orders: OrderCreationRepository,
        public_codes: PublicOrderCodeGenerator,
    ) -> None:
        self._customers = customers
        self._wallets = wallets
        self._networks = networks
        self._payments = payments
        self._orders = orders
        self._public_codes = public_codes

    async def create(self, command: CreatePurchaseOrderCommand) -> object:
        identity = await self._customers.get_payment_identity(command.user_id)
        if identity is None:
            raise ValueError("customer payment identity is not verified")

        wallet = await self._wallets.get_verified_for_user(command.wallet_id, command.user_id)
        if wallet is None:
            raise LookupError("verified wallet not found for customer")

        network = await self._networks.get_enabled(command.network_code)
        if network is None or not network.enabled:
            raise ValueError("selected network is unavailable")

        validate_wallet_for_order(
            wallet,
            command.user_id,
            network,
            command.requested_amount,
        )

        payment_account = await self._payments.get_admin_payment_account()
        if payment_account is None:
            raise RuntimeError("admin payment account is not configured")

        financials = OrderFinancials.calculate(
            requested_amount=command.requested_amount,
            fee_percent=network.service_fee_percent,
            payment_currency=command.payment_currency,
            exchange_rate=command.exchange_rate,
            rounding_policy_version=command.rounding_policy_version,
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
            financials=financials,
        )
        return await self._orders.create_order_atomically(draft)
