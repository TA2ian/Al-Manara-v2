from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.application.admin_order_listing import (
    AdminOrderListType,
    AdminOrderPage,
    AdminOrderListingService,
    ListAdminOrdersCommand,
)


@dataclass(frozen=True, slots=True)
class TelegramAdminOrderListingInput:
    admin_user_id: int
    actor_type: str
    list_type: str = "active"
    page: int = 0
    page_size: int = 5


@dataclass(frozen=True, slots=True)
class TelegramAdminOrderListingResponse:
    ok: bool
    page: AdminOrderPage | None = None
    message: str = ""


class AdminOrderListingApplication(Protocol):
    async def list(self, command: ListAdminOrdersCommand) -> AdminOrderPage: ...


class TelegramAdminOrderListingHandler:
    def __init__(self, service: AdminOrderListingApplication | AdminOrderListingService) -> None:
        self._service = service

    async def handle(self, request: TelegramAdminOrderListingInput) -> TelegramAdminOrderListingResponse:
        if request.admin_user_id <= 0:
            return TelegramAdminOrderListingResponse(False, message="Invalid administrator identity.")
        if request.page < 0:
            return TelegramAdminOrderListingResponse(False, message="The page is invalid.")
        try:
            AdminOrderListType(request.list_type.strip().lower())
        except (AttributeError, ValueError):
            return TelegramAdminOrderListingResponse(False, message="The order list type is invalid.")
        try:
            result = await self._service.list(ListAdminOrdersCommand(
                admin_telegram_user_id=request.admin_user_id,
                actor_type=request.actor_type,
                list_type=request.list_type,
                page=request.page,
                page_size=request.page_size,
            ))
        except PermissionError:
            return TelegramAdminOrderListingResponse(False, message="You are not authorized to view orders.")
        except ValueError as exc:
            return TelegramAdminOrderListingResponse(False, message=str(exc))
        except RuntimeError:
            return TelegramAdminOrderListingResponse(False, message="Orders could not be loaded. Please retry.")
        except Exception:
            return TelegramAdminOrderListingResponse(False, message="An unexpected error occurred. Please retry.")
        return TelegramAdminOrderListingResponse(True, page=result, message="Orders loaded.")
