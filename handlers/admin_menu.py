from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from handlers.common import (
    build_tickets_list_text,
    is_owner_message,
    is_owner_user,
    send_long_message,
)
from keyboards import ADMIN_BUTTON, admin_menu_inline


router = Router()


@router.message(F.text == ADMIN_BUTTON)
async def show_admin_menu(message: Message, state: FSMContext) -> None:
    if not is_owner_message(message):
        return

    await state.clear()
    await message.answer("⚙️ Панель управления", reply_markup=admin_menu_inline())


@router.callback_query(F.data == "admin_status")
async def admin_status(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_owner_user(callback.from_user):
        await callback.answer("Нет доступа", show_alert=True)
        return

    await state.clear()
    await callback.answer()
    await send_long_message(callback.message, await build_tickets_list_text(admin_status=True))
