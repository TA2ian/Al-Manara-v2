from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.runtime.telegram.admin_order_actions import order_action_markup
from app.runtime.telegram.admin_order_listing import TelegramAdminOrderListingHandler, TelegramAdminOrderListingInput
from app.application.admin_order_review_details import AdminOrderReviewDetailsService, GetAdminOrderReviewDetailsCommand
from app.runtime.telegram.admin_session import TelegramAdminSessionHandler
from app.runtime.telegram.shared.actor import authenticated_telegram_user_id, is_private_message
from app.runtime.telegram.fulfillment import fulfillment_action_markup

ADMIN_DASHBOARD_CALLBACK = "admin:dashboard"
ADMIN_IDENTITY_CALLBACK = "admin:identity_pending"
ADMIN_ORDERS_CALLBACK = "admin:orders"
ADMIN_REVIEW_ORDERS_CALLBACK = "admin:review_orders"
ADMIN_FULFILLMENT_CALLBACK = "admin:fulfillment"
ADMIN_ORDER_PAGE_SIZE = 5


def admin_dashboard_markup(*, include_orders: bool = False) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text="👥 التحقق من المستخدمين", callback_data=ADMIN_IDENTITY_CALLBACK)]]
    if include_orders:
        rows.append([InlineKeyboardButton(text="📦 الطلبات النشطة", callback_data=ADMIN_ORDERS_CALLBACK)])
        rows.append([InlineKeyboardButton(text="🔎 المدفوعات قيد المراجعة", callback_data=ADMIN_REVIEW_ORDERS_CALLBACK)])
        rows.append([InlineKeyboardButton(text="🚚 الطلبات المعتمدة للتنفيذ", callback_data=ADMIN_FULFILLMENT_CALLBACK)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def render_admin_dashboard() -> str:
    return (
        "📊 لوحة تحكم الإدارة\n\n"
        "اختر إحدى العمليات المتاحة.\n"
        "تظهر العمليات هنا فقط بعد اجتياز صلاحيات الإدارة."
    )


def _render_orders(
    page,
    *,
    review_actions: bool = False,
    fulfillment_actions: bool = False,
    current_admin_user_id: int | None = None,
) -> tuple[str, InlineKeyboardMarkup | None]:
    if not page.items:
        if review_actions:
            empty = "لا توجد طلبات قيد المراجعة حاليًا."
        elif fulfillment_actions:
            empty = "لا توجد طلبات معتمدة للتنفيذ حاليًا."
        else:
            empty = "لا توجد طلبات نشطة حاليًا."
        return empty, None
    if review_actions:
        title = "🔎 طلبات قيد المراجعة"
    elif fulfillment_actions:
        title = "🚚 الطلبات المعتمدة للتنفيذ"
    else:
        title = "📦 الطلبات النشطة"
    lines = [f"{title} ({page.total_count})", ""]
    rows: list[list[InlineKeyboardButton]] = []
    for item in page.items:
        lines.append(
            f"• {item.public_order_code} | {item.status}\n"
            f"  العميل: {item.user_telegram_id}\n"
            f"  الشبكة: {item.network_code}"
        )
        if review_actions:
            rows.append([InlineKeyboardButton(text="عرض الإيصال والتفاصيل", callback_data=f"admin:order:view:{item.internal_order_id}:{item.version}")])
            rows.extend(order_action_markup(item.internal_order_id, item.version).inline_keyboard)
        elif fulfillment_actions:
            if item.fulfillment_claimed_by is None:
                rows.extend(
                    fulfillment_action_markup(
                        item.internal_order_id,
                        item.version,
                        claimed=False,
                    ).inline_keyboard
                )
            elif item.fulfillment_claimed_by == current_admin_user_id:
                rows.extend(
                    fulfillment_action_markup(
                        item.internal_order_id,
                        item.version,
                        claimed=True,
                    ).inline_keyboard
                )
            else:
                lines.append("  التنفيذ مستلم من مدير آخر؛ لا يمكن إتمامه من هذا الحساب.")
    if page.total_count > page.page_size:
        lines.append(f"\nالصفحة {page.page + 1}")
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


def build_admin_dashboard_router(
    handler,
    order_listing: TelegramAdminOrderListingHandler | None = None,
    review_details: AdminOrderReviewDetailsService | None = None,
    session_handler: TelegramAdminSessionHandler | None = None,
):
    router = Router(name="admin-dashboard")

    async def authorize(user_id: int):
        return await handler.list_pending(user_id)

    async def show_dashboard(message: Message) -> None:
        if not is_private_message(message):
            await message.answer("لوحة الإدارة متاحة في المحادثة الخاصة مع البوت فقط.")
            return
        user_id = authenticated_telegram_user_id(message)
        if user_id is None:
            await message.answer("تعذر التحقق من هوية المدير.")
            return
        authorization = await authorize(user_id)
        if not authorization.ok:
            await message.answer(authorization.message or "غير مصرح لك بالوصول إلى لوحة الإدارة.")
            return
        await message.answer(
            render_admin_dashboard(),
            reply_markup=admin_dashboard_markup(include_orders=order_listing is not None),
        )

    @router.message(Command("admin"))
    async def admin_command(message: Message) -> None:
        await show_dashboard(message)

    @router.callback_query(F.data == ADMIN_DASHBOARD_CALLBACK)
    async def dashboard_callback(query: CallbackQuery) -> None:
        if query.message is None or not is_private_message(query.message):
            await query.answer("لوحة الإدارة متاحة في المحادثة الخاصة فقط.", show_alert=True)
            return
        user_id = authenticated_telegram_user_id(query)
        if user_id is None:
            await query.answer("تعذر التحقق من هوية المدير.", show_alert=True)
            return
        authorization = await authorize(user_id)
        if not authorization.ok:
            await query.answer(authorization.message or "غير مصرح لك.", show_alert=True)
            return
        await query.answer()
        await query.message.edit_text(
            render_admin_dashboard(),
            reply_markup=admin_dashboard_markup(include_orders=order_listing is not None),
        )

    @router.callback_query(F.data == ADMIN_IDENTITY_CALLBACK)
    async def identity_callback(query: CallbackQuery) -> None:
        if query.message is None or not is_private_message(query.message):
            await query.answer("مراجعة طلبات التحقق متاحة في المحادثة الخاصة فقط.", show_alert=True)
            return
        user_id = authenticated_telegram_user_id(query)
        if user_id is None:
            await query.answer("تعذر التحقق من هوية المدير.", show_alert=True)
            return
        response = await authorize(user_id)
        if not response.ok:
            await query.answer(response.message or "غير مصرح لك.", show_alert=True)
            return
        await query.answer()
        if not response.submissions:
            await query.message.answer("لا توجد طلبات تحقق معلقة.")
            return
        await query.message.answer("للمراجعة التفصيلية أرسل /identity_pending.")

    async def load_order_list(query: CallbackQuery, list_type: str) -> None:
        if query.message is None or not is_private_message(query.message):
            await query.answer("عرض الطلبات متاح في المحادثة الخاصة فقط.", show_alert=True)
            return
        user_id = authenticated_telegram_user_id(query)
        if user_id is None:
            await query.answer("تعذر التحقق من هوية المدير.", show_alert=True)
            return
        authorization = await authorize(user_id)
        if not authorization.ok:
            await query.answer(authorization.message or "غير مصرح لك.", show_alert=True)
            return
        await query.answer()
        response = await order_listing.handle(
            TelegramAdminOrderListingInput(
                admin_user_id=user_id,
                actor_type="primary",
                list_type=list_type,
                page=0,
                page_size=ADMIN_ORDER_PAGE_SIZE,
            )
        )
        if not response.ok or response.page is None:
            await query.message.answer(response.message or "تعذر تحميل الطلبات.")
            return
        is_review_list = list_type == "review"
        is_fulfillment_list = list_type == "fulfillment"
        text, markup = _render_orders(
            response.page,
            review_actions=is_review_list,
            fulfillment_actions=is_fulfillment_list,
            current_admin_user_id=user_id,
        )
        await query.message.answer(text, reply_markup=markup)

    if review_details is not None and session_handler is not None:
        @router.callback_query(F.data.regexp(r"^admin:order:view:[0-9a-fA-F-]{36}:[0-9]+$"))
        async def review_order_details_callback(query: CallbackQuery) -> None:
            if query.message is None or not is_private_message(query.message):
                await query.answer("مراجعة الطلب متاحة في المحادثة الخاصة فقط.", show_alert=True)
                return
            user_id = authenticated_telegram_user_id(query)
            if user_id is None:
                await query.answer("تعذر التحقق من هوية المدير.", show_alert=True)
                return
            try:
                parts = (query.data or "").split(":")
                order_id = __import__("uuid").UUID(parts[3])
                expected_version = int(parts[4])
            except (ValueError, TypeError, IndexError):
                await query.answer("بيانات الطلب غير صالحة.", show_alert=True)
                return
            resolver = getattr(order_listing, "_actor_type_resolver", None)
            actor_type = await resolver.resolve_actor_type(user_id) if resolver is not None else None
            if actor_type not in {"primary", "backup"}:
                await query.answer("تعذر التحقق من صلاحيات المدير.", show_alert=True)
                return
            session = await session_handler.create(user_id, actor_type)
            if not session.ok or session.session is None:
                await query.answer(session.message or "تعذر إنشاء جلسة إدارية حديثة.", show_alert=True)
                return
            try:
                details = await review_details.get(GetAdminOrderReviewDetailsCommand(
                    admin_telegram_user_id=user_id,
                    actor_type=actor_type,
                    order_id=order_id,
                    session_id=session.session.session_id,
                ))
            except Exception:
                await query.answer("تعذر تحميل تفاصيل الطلب.", show_alert=True)
                return
            if details.version != expected_version:
                await query.answer("تغير الطلب. افتح قائمة المراجعة من جديد.", show_alert=True)
                return
            await query.answer()
            lines = [
                f"🔎 الطلب {details.public_order_code}",
                f"الحالة: {details.status}",
                f"الإصدار: {details.version}",
                f"العميل: {details.user_telegram_id}",
                f"الشبكة: {details.network_code}",
                f"المبلغ المطلوب: {details.requested_amount}",
                f"عملة الدفع: {details.payment_currency}",
                f"المبلغ المحلي المطلوب: {details.local_amount}",
            ]
            if details.receipt_submission_id is None or not details.receipt_telegram_file_id:
                lines.append("الإيصال: لا يوجد إيصال مرفوع.")
                await query.message.answer("\n".join(lines))
                return
            lines.extend([
                f"محاولة الإيصال: {details.receipt_attempt_number}",
                f"حالة الإيصال: {details.receipt_processing_status}",
                f"حالة الربط: {details.receipt_linkage_status}",
                "تحقق بصري: قارن الإيصال المرفق مع المبلغ والعملة أعلاه قبل الاعتماد.",
            ])
            await query.message.answer("\n".join(lines))
            try:
                await query.message.answer_document(details.receipt_telegram_file_id)
            except Exception:
                try:
                    await query.message.answer_photo(details.receipt_telegram_file_id)
                except Exception:
                    await query.message.answer("تعذر إرسال الإيصال، لكن بيانات المراجعة بقيت محفوظة.")

    if order_listing is not None:
        @router.callback_query(F.data == ADMIN_ORDERS_CALLBACK)
        async def orders_callback(query: CallbackQuery) -> None:
            await load_order_list(query, "active")

        @router.callback_query(F.data == ADMIN_REVIEW_ORDERS_CALLBACK)
        async def review_orders_callback(query: CallbackQuery) -> None:
            await load_order_list(query, "review")

        @router.callback_query(F.data == ADMIN_FULFILLMENT_CALLBACK)
        async def fulfillment_callback(query: CallbackQuery) -> None:
            await load_order_list(query, "fulfillment")

    return router
