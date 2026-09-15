from __future__ import annotations

from aiogram import F, Router
from aiogram.types import Message

from app.composition_root import CustomerComposition
from app.runtime.telegram.customer.dashboard import build_customer_dashboard_router
from app.runtime.telegram.customer.identity import build_customer_identity_router
from app.runtime.telegram.customer.orders import build_customer_orders_router
from app.runtime.telegram.customer.purchase_order import build_customer_purchase_order_router
from app.runtime.telegram.customer.wallets import build_customer_wallets_router


def render_command_help() -> str:
    return (
        "مرحبًا بك في المنارة.\n"
        "استخدم /start لفتح لوحة المنارة، /verify للتحقق من الهوية، "
        "/wallets لإدارة المحافظ، /buy لإنشاء طلب شراء، أو /orders لعرض طلباتك."
    )


def build_customer_router(composition: CustomerComposition) -> Router:
    router = Router(name="customer")
    router.include_router(build_customer_dashboard_router(composition))
    router.include_router(build_customer_wallets_router(composition))
    router.include_router(build_customer_purchase_order_router(composition))
    router.include_router(build_customer_orders_router(composition))
    router.include_router(build_customer_identity_router(composition))

    fallback = Router(name="customer-navigation")

    @fallback.message(F.text.startswith("/"))
    async def show_unknown_command(message: Message) -> None:
        await message.answer(render_command_help())

    router.include_router(fallback)
    return router
