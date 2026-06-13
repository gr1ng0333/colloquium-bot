from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message

from database import get_ticket, update_ticket_image
from handlers.common import (
    MAX_TICKET_IMAGES,
    delete_ticket_images,
    finish_fsm,
    is_owner_message,
    is_owner_user,
    next_ticket_image_index,
    parse_ticket_number,
    ticket_image_count,
    ticket_image_path,
    ticket_image_paths,
)
from keyboards import cancel_keyboard, image_actions_inline, main_keyboard
from states import ManageImage


router = Router()


async def _ask_for_image(message: Message, state: FSMContext, ticket_number: int, image_index: int) -> None:
    await state.update_data(next_image_index=image_index)
    await state.set_state(ManageImage.waiting_for_image)
    await message.answer(
        f"Отправь график {image_index}/{MAX_TICKET_IMAGES}:",
        reply_markup=cancel_keyboard(),
    )


@router.callback_query(F.data == "admin_image")
async def start_image_manage(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_owner_user(callback.from_user):
        await callback.answer("Нет доступа", show_alert=True)
        return

    await state.clear()
    await state.set_state(ManageImage.waiting_for_number)
    await callback.answer()
    await callback.message.answer(
        "К какому билету добавить/заменить график? (1–43):",
        reply_markup=cancel_keyboard(),
    )


@router.message(ManageImage.waiting_for_number, F.text)
async def receive_image_number(message: Message, state: FSMContext) -> None:
    if not is_owner_message(message):
        return

    ticket_number = parse_ticket_number(message.text)
    if ticket_number is None:
        await message.answer("Нужно число от 1 до 43.")
        return

    ticket = await get_ticket(ticket_number)
    if not ticket:
        await state.clear()
        await finish_fsm(message, f"Билет {ticket_number} не загружен. Сначала загрузи текст.")
        return

    await state.update_data(ticket_number=ticket_number)
    image_paths = ticket_image_paths(ticket_number)
    if not image_paths:
        if ticket["has_image"]:
            await update_ticket_image(ticket_number, has_image=False)
        await _ask_for_image(message, state, ticket_number, 1)
        return

    await state.set_state(ManageImage.waiting_for_action)
    for index, image_path in enumerate(image_paths, start=1):
        await message.bot.send_photo(
            chat_id=message.chat.id,
            photo=FSInputFile(image_path),
            caption=f"Текущий график {index}/{len(image_paths)} билета {ticket_number}",
        )

    await message.answer(
        f"У билета {ticket_number} сейчас {len(image_paths)}/{MAX_TICKET_IMAGES} графиков. Что сделать?",
        reply_markup=image_actions_inline(can_add=len(image_paths) < MAX_TICKET_IMAGES),
    )


@router.message(ManageImage.waiting_for_number)
async def invalid_image_number(message: Message) -> None:
    if is_admin_message(message):
        await message.answer("Нужно число от 1 до 43.")


@router.callback_query(ManageImage.waiting_for_action, F.data == "imgact_add")
async def add_image(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_owner_user(callback.from_user):
        await callback.answer("Нет доступа", show_alert=True)
        return

    data = await state.get_data()
    ticket_number = data["ticket_number"]
    next_index = next_ticket_image_index(ticket_number)
    if next_index is None:
        await callback.answer(f"Уже загружено {MAX_TICKET_IMAGES} графиков", show_alert=True)
        return

    await callback.answer()
    await _ask_for_image(callback.message, state, ticket_number, next_index)


@router.callback_query(ManageImage.waiting_for_action, F.data == "imgact_replace")
async def replace_image(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_owner_user(callback.from_user):
        await callback.answer("Нет доступа", show_alert=True)
        return

    data = await state.get_data()
    ticket_number = data["ticket_number"]
    await state.update_data(replace_existing_images=True)
    await callback.answer()
    await _ask_for_image(callback.message, state, ticket_number, 1)


@router.callback_query(ManageImage.waiting_for_action, F.data == "imgact_delete")
async def delete_image(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_owner_user(callback.from_user):
        await callback.answer("Нет доступа", show_alert=True)
        return

    data = await state.get_data()
    ticket_number = data["ticket_number"]
    delete_ticket_images(ticket_number)
    await update_ticket_image(ticket_number, has_image=False)
    await state.clear()
    await callback.answer()
    await callback.message.answer(
        f"📊 Графики билета {ticket_number} удалены.",
        reply_markup=main_keyboard(is_admin=True, is_owner=True),
    )


@router.callback_query(ManageImage.waiting_for_action, F.data == "imgact_back")
async def back_from_image(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_owner_user(callback.from_user):
        await callback.answer("Нет доступа", show_alert=True)
        return

    await state.clear()
    await callback.answer()
    await callback.message.answer("Действие отменено.", reply_markup=main_keyboard(is_admin=True, is_owner=True))


@router.message(ManageImage.waiting_for_image)
async def receive_image(message: Message, state: FSMContext) -> None:
    if not is_owner_message(message):
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
    image_index = data.get("next_image_index") or next_ticket_image_index(ticket_number) or 1
    if image_index == 1 and data.get("replace_existing_images"):
        delete_ticket_images(ticket_number)
        await update_ticket_image(ticket_number, has_image=False)
        await state.update_data(replace_existing_images=False)

    image_path = ticket_image_path(ticket_number, image_index)
    image_path.parent.mkdir(parents=True, exist_ok=True)
    await message.bot.download(file_id, destination=image_path)
    await update_ticket_image(ticket_number, has_image=True)

    image_count = ticket_image_count(ticket_number)
    await state.clear()
    await finish_fsm(
        message,
        f"✅ График {image_index}/{MAX_TICKET_IMAGES} билета {ticket_number} сохранён. "
        f"Всего графиков: {image_count}.",
    )
