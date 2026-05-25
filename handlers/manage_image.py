from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message

from database import get_ticket, update_ticket_image
from handlers.common import (
    finish_fsm,
    is_admin_message,
    is_admin_user,
    parse_ticket_number,
    ticket_image_path,
)
from keyboards import cancel_keyboard, image_actions_inline, main_keyboard
from states import ManageImage


router = Router()


@router.callback_query(F.data == "admin_image")
async def start_image_manage(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin_user(callback.from_user):
        await callback.answer("Нет доступа", show_alert=True)
        return

    await state.clear()
    await state.set_state(ManageImage.waiting_for_number)
    await callback.answer()
    await callback.message.answer(
        "К какому билету добавить/заменить график? (1–33):",
        reply_markup=cancel_keyboard(),
    )


@router.message(ManageImage.waiting_for_number, F.text)
async def receive_image_number(message: Message, state: FSMContext) -> None:
    if not is_admin_message(message):
        return

    ticket_number = parse_ticket_number(message.text)
    if ticket_number is None:
        await message.answer("Нужно число от 1 до 33.")
        return

    ticket = await get_ticket(ticket_number)
    if not ticket:
        await state.clear()
        await finish_fsm(message, f"Билет {ticket_number} не загружен. Сначала загрузи текст.")
        return

    await state.update_data(ticket_number=ticket_number)
    image_path = ticket_image_path(ticket_number)
    if not ticket["has_image"] or not image_path.exists():
        if ticket["has_image"]:
            await update_ticket_image(ticket_number, has_image=False)
        await state.set_state(ManageImage.waiting_for_image)
        await message.answer(
            f"У билета {ticket_number} пока нет графика. Отправь картинку:",
            reply_markup=cancel_keyboard(),
        )
        return

    await state.set_state(ManageImage.waiting_for_action)
    await message.bot.send_photo(
        chat_id=message.chat.id,
        photo=FSInputFile(image_path),
        caption=f"Текущий график билета {ticket_number}",
        reply_markup=image_actions_inline(),
    )


@router.message(ManageImage.waiting_for_number)
async def invalid_image_number(message: Message) -> None:
    if is_admin_message(message):
        await message.answer("Нужно число от 1 до 33.")


@router.callback_query(ManageImage.waiting_for_action, F.data == "imgact_replace")
async def replace_image(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin_user(callback.from_user):
        await callback.answer("Нет доступа", show_alert=True)
        return

    await state.set_state(ManageImage.waiting_for_image)
    await callback.answer()
    await callback.message.answer("Отправь новую картинку:", reply_markup=cancel_keyboard())


@router.callback_query(ManageImage.waiting_for_action, F.data == "imgact_delete")
async def delete_image(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin_user(callback.from_user):
        await callback.answer("Нет доступа", show_alert=True)
        return

    data = await state.get_data()
    ticket_number = data["ticket_number"]
    image_path = ticket_image_path(ticket_number)
    if image_path.exists():
        image_path.unlink()

    await update_ticket_image(ticket_number, has_image=False)
    await state.clear()
    await callback.answer()
    await callback.message.answer(
        f"📊 График билета {ticket_number} удалён.",
        reply_markup=main_keyboard(is_admin=True),
    )


@router.callback_query(ManageImage.waiting_for_action, F.data == "imgact_back")
async def back_from_image(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin_user(callback.from_user):
        await callback.answer("Нет доступа", show_alert=True)
        return

    await state.clear()
    await callback.answer()
    await callback.message.answer("Действие отменено.", reply_markup=main_keyboard(is_admin=True))


@router.message(ManageImage.waiting_for_image)
async def receive_image(message: Message, state: FSMContext) -> None:
    if not is_admin_message(message):
        return

    file_id = None
    if message.photo:
        file_id = message.photo[-1].file_id
    elif message.document and (message.document.mime_type or "").startswith("image/"):
        file_id = message.document.file_id

    if file_id is None:
        await message.answer("Нужна картинка. Отправь фото или PNG-файл, или /cancel для отмены.")
        return

    data = await state.get_data()
    ticket_number = data["ticket_number"]
    image_path = ticket_image_path(ticket_number)
    image_path.parent.mkdir(parents=True, exist_ok=True)
    await message.bot.download(file_id, destination=image_path)
    await update_ticket_image(ticket_number, has_image=True)

    await state.clear()
    await finish_fsm(message, f"✅ График билета {ticket_number} сохранён.")
