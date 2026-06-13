from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from database import get_ticket, update_ticket_image, update_ticket_text
from handlers.common import (
    MAX_TICKET_IMAGES,
    collect_text_or_document,
    delete_ticket_images,
    extract_title,
    finish_fsm,
    is_owner_message,
    is_owner_user,
    next_ticket_image_index,
    parse_ticket_number,
    send_raw_text_mono,
    ticket_image_count,
    ticket_image_path,
    ticket_image_paths,
)
from keyboards import (
    cancel_keyboard,
    edit_actions_inline,
    edit_add_more_images_inline,
    main_keyboard,
)
from states import EditTicket


router = Router()


# ── Helpers ──────────────────────────────────────────────────────────


async def _show_edit_menu(target, state: FSMContext, ticket_number: int) -> None:
    """Show the edit actions menu for a ticket.

    `target` is either a Message or CallbackQuery.message.
    """
    ticket = await get_ticket(ticket_number)
    if not ticket:
        await state.clear()
        if isinstance(target, Message):
            await finish_fsm(target, f"Билет {ticket_number} не найден в базе.")
        return

    await state.update_data(ticket_number=ticket_number)
    await state.set_state(EditTicket.waiting_for_action)

    img_count = ticket_image_count(ticket_number)
    has_images = img_count > 0
    can_add = img_count < MAX_TICKET_IMAGES
    image_text = f"📊 {img_count}/{MAX_TICKET_IMAGES}" if has_images else "❌ нет"

    await target.answer(
        f"📝 Билет {ticket_number}\n"
        f"Заголовок: {ticket['title']}\n"
        f"Символов: {len(ticket['raw_text'])}\n"
        f"Графики: {image_text}\n\n"
        "Что сделать?",
        reply_markup=edit_actions_inline(has_images=has_images, can_add_image=can_add),
    )


# ── Entry point ──────────────────────────────────────────────────────


@router.callback_query(F.data == "admin_edit")
async def start_edit(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_owner_user(callback.from_user):
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
    if not is_owner_message(message):
        return

    ticket_number = parse_ticket_number(message.text)
    if ticket_number is None:
        await message.answer("Нужно число от 1 до 43.")
        return

    await _show_edit_menu(message, state, ticket_number)


@router.message(EditTicket.waiting_for_number)
async def invalid_edit_number(message: Message) -> None:
    if is_admin_message(message):
        await message.answer("Нужно число от 1 до 43.")


# ── Export raw text ──────────────────────────────────────────────────


@router.callback_query(EditTicket.waiting_for_action, F.data == "edit_export_raw")
async def export_raw_text(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_owner_user(callback.from_user):
        await callback.answer("Нет доступа", show_alert=True)
        return

    data = await state.get_data()
    ticket_number = data["ticket_number"]
    ticket = await get_ticket(ticket_number)
    if not ticket:
        await state.clear()
        await callback.answer()
        await callback.message.answer(
            f"Билет {ticket_number} не найден.",
            reply_markup=main_keyboard(is_admin=True, is_owner=True),
        )
        return

    await callback.answer()
    await callback.message.answer(
        f"📄 Исходный текст билета {ticket_number} ({len(ticket['raw_text'])} символов):\n"
        "Скопируй, отредактируй и отправь обратно через «✏️ Заменить текст»."
    )
    await send_raw_text_mono(callback.message, ticket["raw_text"])

    # Return to edit menu
    await _show_edit_menu(callback.message, state, ticket_number)


# ── Replace text ─────────────────────────────────────────────────────


@router.callback_query(EditTicket.waiting_for_action, F.data == "edit_replace_text")
async def choose_replace_text(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_owner_user(callback.from_user):
        await callback.answer("Нет доступа", show_alert=True)
        return

    data = await state.get_data()
    await state.set_state(EditTicket.waiting_for_new_text)
    await callback.answer()
    await callback.message.answer(
        f"Отправь новый текст билета {data['ticket_number']} "
        "(сообщением или .txt файлом):",
        reply_markup=cancel_keyboard(),
    )


@router.message(EditTicket.waiting_for_new_text)
async def receive_new_text(message: Message, state: FSMContext) -> None:
    if not is_owner_message(message):
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
    if not is_owner_message(message):
        return

    data = await state.get_data()
    ticket_number = data.get("ticket_number")
    if ticket_number is None:
        return
    await update_ticket_text(ticket_number, extract_title(raw_text), raw_text)

    parts_text = f" Склеено из {part_count} сообщений." if part_count > 1 else ""
    await message.answer(
        f"✅ Текст билета {ticket_number} обновлён.{parts_text}"
    )

    # Return to edit menu instead of exiting
    await _show_edit_menu(message, state, ticket_number)


# ── Add image (without rewriting ticket) ─────────────────────────────


@router.callback_query(EditTicket.waiting_for_action, F.data == "edit_add_image")
async def edit_add_image(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_owner_user(callback.from_user):
        await callback.answer("Нет доступа", show_alert=True)
        return

    data = await state.get_data()
    ticket_number = data["ticket_number"]
    next_index = next_ticket_image_index(ticket_number)
    if next_index is None:
        await callback.answer(
            f"Уже загружено {MAX_TICKET_IMAGES} графиков", show_alert=True
        )
        return

    await state.update_data(next_image_index=next_index)
    await state.set_state(EditTicket.waiting_for_image)
    await callback.answer()
    await callback.message.answer(
        f"Отправь график {next_index}/{MAX_TICKET_IMAGES}:",
        reply_markup=cancel_keyboard(),
    )


@router.message(EditTicket.waiting_for_image)
async def edit_receive_image(message: Message, state: FSMContext) -> None:
    if not is_owner_message(message):
        return

    file_id = None
    if message.photo:
        file_id = message.photo[-1].file_id
    elif message.document and (message.document.mime_type or "").startswith("image/"):
        file_id = message.document.file_id

    if file_id is None:
        await message.answer(
            "Нужна картинка. Отправь фото или PNG-файл, или /cancel для отмены."
        )
        return

    data = await state.get_data()
    ticket_number = data["ticket_number"]
    image_index = data.get("next_image_index") or next_ticket_image_index(ticket_number) or 1

    if image_index == 1 and data.get("replace_existing_images"):
        delete_ticket_images(ticket_number)
        await update_ticket_image(ticket_number, has_image=False)
        await state.update_data(replace_existing_images=False)

    img_path = ticket_image_path(ticket_number, image_index)
    img_path.parent.mkdir(parents=True, exist_ok=True)
    await message.bot.download(file_id, destination=img_path)
    await update_ticket_image(ticket_number, has_image=True)

    current_count = ticket_image_count(ticket_number)
    if current_count >= MAX_TICKET_IMAGES:
        await message.answer(
            f"✅ График {image_index}/{MAX_TICKET_IMAGES} сохранён. "
            f"Все {MAX_TICKET_IMAGES} слотов заняты."
        )
        await _show_edit_menu(message, state, ticket_number)
        return

    await state.set_state(EditTicket.waiting_for_more_images)
    await message.answer(
        f"✅ График {image_index}/{MAX_TICKET_IMAGES} сохранён. "
        f"Всего: {current_count}/{MAX_TICKET_IMAGES}. Добавить ещё?",
        reply_markup=edit_add_more_images_inline(),
    )


@router.callback_query(EditTicket.waiting_for_more_images, F.data == "edit_img_more")
async def edit_add_more_image(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_owner_user(callback.from_user):
        await callback.answer("Нет доступа", show_alert=True)
        return

    data = await state.get_data()
    ticket_number = data["ticket_number"]
    next_index = next_ticket_image_index(ticket_number)
    if next_index is None:
        await callback.answer(
            f"Уже загружено {MAX_TICKET_IMAGES} графиков", show_alert=True
        )
        await _show_edit_menu(callback.message, state, ticket_number)
        return

    await state.update_data(next_image_index=next_index)
    await state.set_state(EditTicket.waiting_for_image)
    await callback.answer()
    await callback.message.answer(
        f"Отправь график {next_index}/{MAX_TICKET_IMAGES}:",
        reply_markup=cancel_keyboard(),
    )


@router.callback_query(EditTicket.waiting_for_more_images, F.data == "edit_img_done")
async def edit_finish_images(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_owner_user(callback.from_user):
        await callback.answer("Нет доступа", show_alert=True)
        return

    data = await state.get_data()
    ticket_number = data["ticket_number"]
    count = ticket_image_count(ticket_number)
    await callback.answer()
    await callback.message.answer(
        f"✅ Готово. У билета {ticket_number} сейчас {count}/{MAX_TICKET_IMAGES} графиков."
    )
    await _show_edit_menu(callback.message, state, ticket_number)


# ── Replace all images ───────────────────────────────────────────────


@router.callback_query(EditTicket.waiting_for_action, F.data == "edit_replace_images")
async def edit_replace_images(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_owner_user(callback.from_user):
        await callback.answer("Нет доступа", show_alert=True)
        return

    data = await state.get_data()
    ticket_number = data["ticket_number"]
    await state.update_data(next_image_index=1, replace_existing_images=True)
    await state.set_state(EditTicket.waiting_for_image)
    await callback.answer()
    await callback.message.answer(
        f"Старые графики билета {ticket_number} будут заменены.\n"
        f"Отправь новый график 1/{MAX_TICKET_IMAGES}:",
        reply_markup=cancel_keyboard(),
    )


# ── Delete all images ────────────────────────────────────────────────


@router.callback_query(EditTicket.waiting_for_action, F.data == "edit_delete_images")
async def edit_delete_images(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_owner_user(callback.from_user):
        await callback.answer("Нет доступа", show_alert=True)
        return

    data = await state.get_data()
    ticket_number = data["ticket_number"]
    delete_ticket_images(ticket_number)
    await update_ticket_image(ticket_number, has_image=False)

    await callback.answer()
    await callback.message.answer(f"📊 Графики билета {ticket_number} удалены.")
    await _show_edit_menu(callback.message, state, ticket_number)


# ── Back ─────────────────────────────────────────────────────────────


@router.callback_query(EditTicket.waiting_for_action, F.data == "edit_back")
async def back_from_edit(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_owner_user(callback.from_user):
        await callback.answer("Нет доступа", show_alert=True)
        return

    await state.clear()
    await callback.answer()
    await callback.message.answer(
        "Редактирование отменено.", reply_markup=main_keyboard(is_admin=True, is_owner=True)
    )
