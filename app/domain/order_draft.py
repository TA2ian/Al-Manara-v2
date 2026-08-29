from dataclasses import dataclass
from uuid import UUID

from app.domain.money import OrderFinancials
from app.domain.network import NetworkCode
from app.domain.payment_identity import AdminPaymentAccountSnapshot, CustomerPaymentIdentity


@dataclass(frozen=True, slots=True)
class PurchaseOrderDraft:
    internal_order_id: UUID
    public_order_code: str
    user_id: int
    wallet_id: UUID
    network: NetworkCode
    wallet_address: str
    customer_payment_identity: CustomerPaymentIdentity
    admin_payment_account: AdminPaymentAccountSnapshot
    financials: OrderFinancials
