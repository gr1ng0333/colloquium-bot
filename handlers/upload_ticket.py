from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from database import get_ticket, upsert_ticket
from handlers.common import (
    collect_text_or_document,
    extract_title,
    finish_fsm,
    is_admin_message,
    is_admin_user,
    parse_ticket_number,
    ticket_image_path,
)
from keyboards import (
    cancel_keyboard,
    confirm_overwrite_inline,
    image_choice_inline,
    main_keyboard,
)
from states import UploadTicket


router = Router()


async def _ask_for_text(message: Message, state: FSMContext, ticket_number: int) -> None:
    await state.set_state(UploadTicket.waiting_for_text)
    await message.answer(
        f"Отправь текст билета {ticket_number} (сообщением или .txt файлом):",
        reply_markup=cancel_keyboard(),
    )


@router.callback_query(F.data == "admin_upload")
async def start_upload(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin_user(callback.from_user):
        await callback.answer("Нет доступа", show_alert=True)
        return

    await state.clear()
    await state.set_state(UploadTicket.waiting_for_number)
    await callback.answer()
    await callback.message.answer(
        "Отправь номер билета (1–33):",
        reply_markup=cancel_keyboard(),
    )


@router.message(UploadTicket.waiting_for_number, F.text)
async def receive_ticket_number(message: Message, state: FSMContext) -> None:
    if not is_admin_message(message):
        return

    ticket_number = parse_ticket_number(message.text)
    if ticket_number is None:
        await message.answer("Нужно число от 1 до 33.")
        return

    await state.update_data(ticket_number=ticket_number)
    existing_ticket = await get_ticket(ticket_number)
    if existing_ticket:
        await message.answer(
            f"⚠️ Билет {ticket_number} уже загружен. Перезаписать?",
            reply_markup=confirm_overwrite_inline(),
        )
        return

    await _ask_for_text(message, state, ticket_number)


@router.message(UploadTicket.waiting_for_number)
async def invalid_ticket_number(message: Message) -> None:
    if is_admin_message(message):
        await message.answer("Нужно число от 1 до 33.")


@router.callback_query(UploadTicket.waiting_for_number, F.data == "overwrite_yes")
async def confirm_overwrite(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin_user(callback.from_user):
        await callback.answer("Нет доступа", show_alert=True)
        return

    data = await state.get_data()
    await callback.answer()
    await _ask_for_text(callback.message, state, data["ticket_number"])


@router.callback_query(UploadTicket.waiting_for_number, F.data == "overwrite_cancel")
async def cancel_overwrite(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin_user(callback.from_user):
        await callback.answer("Нет доступа", show_alert=True)
        return

    await state.clear()
    await callback.answer()
    await callback.message.answer(
        "Действие отменено.",
        reply_markup=main_keyboard(is_admin=True),
    )


@router.message(UploadTicket.waiting_for_text)
async def receive_ticket_text(message: Message, state: FSMContext) -> None:
    if not is_admin_message(message):
        return

    handled = await collect_text_or_document(
        message=message,
        state=state,
        expected_state=UploadTicket.waiting_for_text.state,
        finalize=_finalize_ticket_text,
    )
    if not handled:
        await message.answer("Нужен текст или .txt файл.")
        return


async def _finalize_ticket_text(
    message: Message,
    state: FSMContext,
    raw_text: str,
    part_count: int,
) -> None:
    if not is_admin_message(message):
        return

    title = extract_title(raw_text)
    await state.update_data(raw_text=raw_text, title=title)
    await state.set_state(UploadTicket.waiting_for_image_choice)

    parts_text = f", склеено из {part_count} сообщений" if part_count > 1 else ""
    await message.answer(
        f"✅ Текст принят ({len(raw_text)} символов{parts_text}). "
        f"Первая строка: «{title}»\n\nЕсть график?",
        reply_markup=image_choice_inline(),
    )


@router.callback_query(UploadTicket.waiting_for_image_choice, F.data == "img_no")
async def choose_no_image(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin_user(callback.from_user):
        await callback.answer("Нет доступа", show_alert=True)
        return

    data = await state.get_data()
    ticket_number = data["ticket_number"]
    await upsert_ticket(ticket_number, data["title"], data["raw_text"], has_image=False)

    image_path = ticket_image_path(ticket_number)
    if image_path.exists():
        image_path.unlink()

    await state.clear()
    await callback.answer()
    await callback.message.answer(
        f"✅ Билет {ticket_number} сохранён.",
        reply_markup=main_keyboard(is_admin=True),
    )


@router.callback_query(UploadTicket.waiting_for_image_choice, F.data == "img_yes")
async def choose_yes_image(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin_user(callback.from_user):
        await callback.answer("Нет доступа", show_alert=True)
        return

    await state.set_state(UploadTicket.waiting_for_image)
    await callback.answer()
    await callback.message.answer(
        "Отправь картинку (фото или PNG-файл):",
        reply_markup=cancel_keyboard(),
    )


@router.message(UploadTicket.waiting_for_image)
async def receive_ticket_image(message: Message, state: FSMContext) -> None:
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
    await upsert_ticket(ticket_number, data["title"], data["raw_text"], has_image=True)

    await state.clear()
    await finish_fsm(message, f"✅ Билет {ticket_number} сохранён с графиком.")
