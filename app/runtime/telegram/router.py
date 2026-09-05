from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from app.composition_root import CustomerComposition
from app.runtime.telegram.customer.identity import build_customer_identity_router
from app.runtime.telegram.customer.orders import build_customer_orders_router


def render_command_help() -> str:
    return (
        "مرحبًا بك في المنارة.\n"
        "استخدم /verify لإرسال بيانات التحقق، و/orders لعرض حالة طلباتك وسجلها."
    )


def build_customer_router(composition: CustomerComposition) -> Router:
    router = Router(name="customer")
    router.include_router(build_customer_orders_router(composition))
    router.include_router(build_customer_identity_router(composition))

    fallback = Router(name="customer-navigation")

    @fallback.message(CommandStart())
    @fallback.message(F.text.startswith("/start "))
    async def show_command_help(message: Message) -> None:
        await message.answer(render_command_help())

    @fallback.message(F.text.startswith("/"))
    async def show_unknown_command(message: Message) -> None:
        await message.answer(render_command_help())

    router.include_router(fallback)
    return router