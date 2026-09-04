from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.application.admin_order_closure import AdminOrderClosureService
from app.application.admin_order_listing import AdminOrderListingService
from app.application.admin_order_review import AdminOrderReviewService
from app.application.admin_session import AdminSessionService
from app.application.fulfillment import FulfillmentService
from app.application.order_service import OrderTransitionService
from app.application.uow import UnitOfWork
from app.infrastructure.persistence.admin_authorization_repository import (
    SupabaseAdminAuthorizationRepository,
)
from app.infrastructure.persistence.admin_order_closure_repository import (
    SupabaseAdminOrderClosureRepository,
)
from app.infrastructure.persistence.admin_order_listing_repository import (
    SupabaseAdminOrderListingRepository,
)
from app.infrastructure.persistence.admin_session_repository import SupabaseAdminSessionRepository
from app.infrastructure.persistence.fulfillment_repository import SupabaseFulfillmentRepository
from app.runtime.telegram.admin_order_closure import TelegramAdminOrderClosureHandler
from app.runtime.telegram.admin_order_listing import TelegramAdminOrderListingHandler
from app.runtime.telegram.admin_order_review import TelegramAdminOrderReviewHandler
from app.runtime.telegram.admin_session import TelegramAdminSessionHandler
from app.runtime.telegram.fulfillment import TelegramFulfillmentHandler


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
