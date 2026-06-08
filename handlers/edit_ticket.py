from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from database import get_ticket, update_ticket_text
from handlers.common import (
    collect_text_or_document,
    extract_title,
    finish_fsm,
    is_admin_message,
    is_admin_user,
    parse_ticket_number,
)
from keyboards import cancel_keyboard, edit_actions_inline, main_keyboard
from states import EditTicket


router = Router()


@router.callback_query(F.data == "admin_edit")
async def start_edit(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin_user(callback.from_user):
        await callback.answer("Нет доступа", show_alert=True)
        return

    await state.clear()
    await state.set_state(EditTicket.waiting_for_number)
    await callback.answer()
    await callback.message.answer(
        "Какой билет редактировать? (1–43):",
        reply_markup=cancel_keyboard(),
    )


@router.message(EditTicket.waiting_for_number, F.text)
async def receive_edit_number(message: Message, state: FSMContext) -> None:
    if not is_admin_message(message):
        return

    ticket_number = parse_ticket_number(message.text)
    if ticket_number is None:
        await message.answer("Нужно число от 1 до 43.")
        return

    ticket = await get_ticket(ticket_number)
    if not ticket:
        await state.clear()
        await finish_fsm(message, f"Билет {ticket_number} не загружен. Сначала загрузи его через ➕.")
        return

    await state.update_data(ticket_number=ticket_number)
    await state.set_state(EditTicket.waiting_for_action)
    image_text = "✅ есть" if ticket["has_image"] else "❌ нет"
    await message.answer(
        f"📝 Билет {ticket_number}\n"
        f"Заголовок: {ticket['title']}\n"
        f"Символов: {len(ticket['raw_text'])}\n"
        f"График: {image_text}\n\n"
        "Что изменить?",
        reply_markup=edit_actions_inline(),
    )


@router.message(EditTicket.waiting_for_number)
async def invalid_edit_number(message: Message) -> None:
    if is_admin_message(message):
        await message.answer("Нужно число от 1 до 43.")


@router.callback_query(EditTicket.waiting_for_action, F.data == "edit_replace_text")
async def choose_replace_text(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin_user(callback.from_user):
        await callback.answer("Нет доступа", show_alert=True)
        return

    data = await state.get_data()
    await state.set_state(EditTicket.waiting_for_new_text)
    await callback.answer()
    await callback.message.answer(
        f"Отправь новый текст билета {data['ticket_number']}:",
        reply_markup=cancel_keyboard(),
    )


@router.callback_query(EditTicket.waiting_for_action, F.data == "edit_back")
async def back_from_edit(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin_user(callback.from_user):
        await callback.answer("Нет доступа", show_alert=True)
        return

    await state.clear()
    await callback.answer()
    await callback.message.answer("Редактирование отменено.", reply_markup=main_keyboard(is_admin=True))


@router.message(EditTicket.waiting_for_new_text)
async def receive_new_text(message: Message, state: FSMContext) -> None:
    if not is_admin_message(message):
        return

    handled = await collect_text_or_document(
        message=message,
        state=state,
        expected_state=EditTicket.waiting_for_new_text.state,
        finalize=_finalize_new_text,
    )
    if not handled:
        await message.answer("Нужен текст или .txt файл.")
        return


async def _finalize_new_text(
    message: Message,
    state: FSMContext,
    raw_text: str,
    part_count: int,
) -> None:
    if not is_admin_message(message):
        return

    data = await state.get_data()
    ticket_number = data["ticket_number"]
    await update_ticket_text(ticket_number, extract_title(raw_text), raw_text)
    await state.clear()
    parts_text = f" Склеено из {part_count} сообщений." if part_count > 1 else ""
    await finish_fsm(message, f"✅ Текст билета {ticket_number} обновлён.{parts_text}")
