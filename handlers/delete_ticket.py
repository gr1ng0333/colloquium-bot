from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from database import delete_ticket, get_ticket
from handlers.common import (
    finish_fsm,
    is_admin_message,
    is_admin_user,
    parse_ticket_number,
    ticket_image_path,
)
from keyboards import cancel_keyboard, confirm_delete_inline, main_keyboard
from states import DeleteTicket


router = Router()


@router.callback_query(F.data == "admin_delete")
async def start_delete(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin_user(callback.from_user):
        await callback.answer("Нет доступа", show_alert=True)
        return

    await state.clear()
    await state.set_state(DeleteTicket.waiting_for_number)
    await callback.answer()
    await callback.message.answer(
        "Какой билет удалить? (1–33):",
        reply_markup=cancel_keyboard(),
    )


@router.message(DeleteTicket.waiting_for_number, F.text)
async def receive_delete_number(message: Message, state: FSMContext) -> None:
    if not is_admin_message(message):
        return

    ticket_number = parse_ticket_number(message.text)
    if ticket_number is None:
        await message.answer("Нужно число от 1 до 33.")
        return

    ticket = await get_ticket(ticket_number)
    if not ticket:
        await state.clear()
        await finish_fsm(message, f"Билет {ticket_number} не найден в базе.")
        return

    await state.update_data(ticket_number=ticket_number)
    await state.set_state(DeleteTicket.waiting_for_confirmation)
    await message.answer(
        f"Удалить билет {ticket_number} «{ticket['title']}»? Это действие необратимо.",
        reply_markup=confirm_delete_inline(ticket_number),
    )


@router.message(DeleteTicket.waiting_for_number)
async def invalid_delete_number(message: Message) -> None:
    if is_admin_message(message):
        await message.answer("Нужно число от 1 до 33.")


@router.callback_query(DeleteTicket.waiting_for_confirmation, F.data.startswith("del_confirm_"))
async def confirm_delete(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin_user(callback.from_user):
        await callback.answer("Нет доступа", show_alert=True)
        return

    data = await state.get_data()
    ticket_number = data["ticket_number"]
    await delete_ticket(ticket_number)

    image_path = ticket_image_path(ticket_number)
    if image_path.exists():
        image_path.unlink()

    await state.clear()
    await callback.answer()
    await callback.message.answer(
        f"✅ Билет {ticket_number} удалён.",
        reply_markup=main_keyboard(is_admin=True),
    )


@router.callback_query(DeleteTicket.waiting_for_confirmation, F.data == "del_cancel")
async def cancel_delete(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin_user(callback.from_user):
        await callback.answer("Нет доступа", show_alert=True)
        return

    await state.clear()
    await callback.answer()
    await callback.message.answer("Удаление отменено.", reply_markup=main_keyboard(is_admin=True))
