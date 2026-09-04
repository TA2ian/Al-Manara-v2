from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from app.application.admin_order_closure import AdminOrderClosureService
from app.application.admin_order_listing import AdminOrderListingService
from app.application.admin_order_review import AdminOrderReviewService
from app.application.admin_session import AdminSessionService
from app.application.create_purchase_order import CreatePurchaseOrderService
from app.application.fulfillment import FulfillmentService
from app.application.order_service import OrderTransitionService
from app.application.uow import UnitOfWork
from app.infrastructure.persistence.admin_authorization_repository import SupabaseAdminAuthorizationRepository
from app.infrastructure.persistence.admin_order_closure_repository import SupabaseAdminOrderClosureRepository
from app.infrastructure.persistence.admin_order_listing_repository import SupabaseAdminOrderListingRepository
from app.infrastructure.persistence.admin_session_repository import SupabaseAdminSessionRepository
from app.infrastructure.persistence.fulfillment_repository import SupabaseFulfillmentRepository
from app.infrastructure.persistence.order_creation_repository import SupabaseOrderCreationRepository
from app.infrastructure.persistence.order_support_repositories import (
    SupabaseCustomerRepository,
    SupabaseNetworkOrderRepository,
    SupabasePaymentSettingsRepository,
)
from app.infrastructure.persistence.quote_support_repository import (
    SupabaseExchangeRateProvider,
    SupabaseFeePolicyProvider,
    UtcQuoteClock,
    UuidPublicOrderCodeGenerator,
)
from app.infrastructure.persistence.wallet_repository import SupabaseWalletRepository
from app.runtime.telegram.admin_order_closure import TelegramAdminOrderClosureHandler
from app.runtime.telegram.admin_order_listing import TelegramAdminOrderListingHandler
from app.runtime.telegram.admin_order_review import TelegramAdminOrderReviewHandler
from app.runtime.telegram.admin_session import TelegramAdminSessionHandler
from app.runtime.telegram.fulfillment import TelegramFulfillmentHandler
from app.runtime.telegram.order_creation_handler import TelegramOrderCreationHandler


@dataclass(frozen=True, slots=True)
class AdminComposition:
    """Fully wired admin application/runtime slice.

    The Telegram framework and Supabase client lifecycle stay outside this module.
    A UnitOfWork is injected because its transaction boundary is an infrastructure
    concern and must not be fabricated by the composition root.
    """

    review: TelegramAdminOrderReviewHandler
    listing: TelegramAdminOrderListingHandler
    closure: TelegramAdminOrderClosureHandler
    session: TelegramAdminSessionHandler
    fulfillment: TelegramFulfillmentHandler


@dataclass(frozen=True, slots=True)
class CustomerComposition:
    """Fully wired customer order-creation runtime slice."""

    order_creation: TelegramOrderCreationHandler


def build_admin_composition(client: Any, order_uow: UnitOfWork) -> AdminComposition:
    """Build the complete admin runtime slice from infrastructure dependencies."""
    authorization = SupabaseAdminAuthorizationRepository(client)
    transitions = OrderTransitionService(order_uow)
    review_service = AdminOrderReviewService(transitions, authorization)

    listing_service = AdminOrderListingService(SupabaseAdminOrderListingRepository(client))
    closure_service = AdminOrderClosureService(SupabaseAdminOrderClosureRepository(client))
    session_service = AdminSessionService(SupabaseAdminSessionRepository(client))
    fulfillment_service = FulfillmentService(SupabaseFulfillmentRepository(client))

    return AdminComposition(
        review=TelegramAdminOrderReviewHandler(review_service),
        listing=TelegramAdminOrderListingHandler(listing_service),
        closure=TelegramAdminOrderClosureHandler(closure_service),
        session=TelegramAdminSessionHandler(session_service),
        fulfillment=TelegramFulfillmentHandler(fulfillment_service),
    )


def build_customer_composition(client: Any) -> CustomerComposition:
    """Build the customer order-creation slice from real persistence adapters."""
    order_service = CreatePurchaseOrderService(
        customers=SupabaseCustomerRepository(client),
        wallets=SupabaseWalletRepository(client),
        networks=SupabaseNetworkOrderRepository(client),
        payments=SupabasePaymentSettingsRepository(client),
        orders=SupabaseOrderCreationRepository(client),
        public_codes=UuidPublicOrderCodeGenerator(),
        exchange_rates=SupabaseExchangeRateProvider(client),
        fee_policies=SupabaseFeePolicyProvider(client),
        clock=UtcQuoteClock(),
        quote_ttl=timedelta(minutes=10),
    )
    return CustomerComposition(order_creation=TelegramOrderCreationHandler(order_service))
