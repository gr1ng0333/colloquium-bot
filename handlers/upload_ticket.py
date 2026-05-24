from __future__ import annotations

from io import BytesIO
from pathlib import Path
import re

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import ADMIN_ID, IMAGES_DIR, TOTAL_TICKETS
from database import (
    delete_ticket,
    get_all_ticket_ids,
    get_ticket,
    get_ticket_count,
    upsert_ticket,
)


router = Router()


class UploadTicket(StatesGroup):
    waiting_for_number = State()
    waiting_for_text = State()
    waiting_for_image_choice = State()
    waiting_for_image = State()


def _is_admin(message: Message) -> bool:
    return bool(message.from_user and message.from_user.id == ADMIN_ID)


def _is_admin_callback(callback: CallbackQuery) -> bool:
    return bool(callback.from_user and callback.from_user.id == ADMIN_ID)


async def _deny_if_not_admin(message: Message) -> bool:
    if _is_admin(message):
        return False

    await message.answer("Нет доступа")
    return True


def _parse_ticket_number(text: str | None) -> int | None:
    if not text:
        return None

    match = re.search(r"\d+", text)
    if not match:
        return None

    number = int(match.group(0))
    if 1 <= number <= TOTAL_TICKETS:
        return number

    return None


def _image_choice_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📊 Да, загрузить график",
                    callback_data="upload:yes_image",
                ),
                InlineKeyboardButton(
                    text="❌ Нет графика",
                    callback_data="upload:no_image",
                ),
            ]
        ]
    )


def _extract_title(raw_text: str) -> str:
    for line in raw_text.splitlines():
        title = line.strip()
        if title:
            return title.replace("**", "")[:200]

    return "Без названия"


def _ticket_image_path(ticket_id: int) -> Path:
    return Path(IMAGES_DIR) / f"ticket_{ticket_id}.png"


async def _read_text_from_message(message: Message) -> str | None:
    if message.text:
        return message.text

    document = message.document
    if not document:
        return None

    is_plain_text = document.mime_type == "text/plain"
    is_txt_file = bool(document.file_name and document.file_name.lower().endswith(".txt"))
    if not (is_plain_text or is_txt_file):
        return None

    buffer = BytesIO()
    await message.bot.download(document.file_id, destination=buffer)
    data = buffer.getvalue()

    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("utf-8", errors="replace")


async def _save_ticket_without_image(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    ticket_number = data["ticket_number"]
    await upsert_ticket(
        ticket_id=ticket_number,
        title=data["title"],
        raw_text=data["raw_text"],
        has_image=False,
    )

    image_path = _ticket_image_path(ticket_number)
    if image_path.exists():
        image_path.unlink()

    await callback.message.answer(f"✅ Билет {ticket_number} сохранён без графика.")
    await state.clear()


@router.message(Command("cancel"))
async def cancel_upload(message: Message, state: FSMContext) -> None:
    if await _deny_if_not_admin(message):
        return

    current_state = await state.get_state()
    if current_state is None:
        return

    await state.clear()
    await message.answer("Загрузка отменена")


@router.message(Command("upload"))
async def start_upload(message: Message, state: FSMContext) -> None:
    if await _deny_if_not_admin(message):
        return

    await state.clear()
    await state.set_state(UploadTicket.waiting_for_number)
    await message.answer("📝 Загрузка билета.\nОтправь номер билета (1–33):")


@router.message(Command("status"))
async def show_status(message: Message) -> None:
    if await _deny_if_not_admin(message):
        return

    loaded_ids = await get_all_ticket_ids()
    loaded = set(loaded_ids)
    missing_ids = [ticket_id for ticket_id in range(1, TOTAL_TICKETS + 1) if ticket_id not in loaded]
    count = await get_ticket_count()

    loaded_text = ", ".join(map(str, loaded_ids)) if loaded_ids else "нет"
    missing_text = ", ".join(map(str, missing_ids)) if missing_ids else "нет"

    await message.answer(
        "📋 Статус загрузки:\n\n"
        f"✅ {loaded_text}\n"
        f"❌ {missing_text}\n\n"
        f"Загружено: {count} / {TOTAL_TICKETS}"
    )


@router.message(Command("delete"))
async def delete_ticket_command(message: Message) -> None:
    if await _deny_if_not_admin(message):
        return

    ticket_number = _parse_ticket_number(message.text)
    if ticket_number is None:
        await message.answer("Неверный номер")
        return

    deleted = await delete_ticket(ticket_number)
    if not deleted:
        await message.answer(f"Билет {ticket_number} не найден в базе")
        return

    image_path = _ticket_image_path(ticket_number)
    if image_path.exists():
        image_path.unlink()

    await message.answer(f"Билет {ticket_number} удалён")


@router.message(UploadTicket.waiting_for_number, F.text)
async def receive_ticket_number(message: Message, state: FSMContext) -> None:
    if await _deny_if_not_admin(message):
        await state.clear()
        return

    ticket_number = _parse_ticket_number(message.text)
    if ticket_number is None:
        await message.answer("Нужно число от 1 до 33. Попробуй ещё раз.")
        return

    await state.update_data(ticket_number=ticket_number)
    await state.set_state(UploadTicket.waiting_for_text)

    existing_ticket = await get_ticket(ticket_number)
    if existing_ticket:
        await message.answer(
            f"⚠️ Билет {ticket_number} уже загружен. Новый текст перезапишет старый. "
            "Отправь текст билета или /cancel для отмены."
        )
        return

    await message.answer(f"Отправь текст билета {ticket_number}:")


@router.message(UploadTicket.waiting_for_number)
async def receive_invalid_ticket_number(message: Message) -> None:
    if await _deny_if_not_admin(message):
        return

    await message.answer("Нужно число от 1 до 33. Попробуй ещё раз.")


@router.message(UploadTicket.waiting_for_text)
async def receive_ticket_text(message: Message, state: FSMContext) -> None:
    if await _deny_if_not_admin(message):
        await state.clear()
        return

    raw_text = await _read_text_from_message(message)
    if not raw_text:
        await message.answer("Отправь текст сообщением или .txt файлом.")
        return

    title = _extract_title(raw_text)
    await state.update_data(raw_text=raw_text, title=title)
    await state.set_state(UploadTicket.waiting_for_image_choice)

    await message.answer(
        f"✅ Текст принят ({len(raw_text)} символов).\n\nЕсть график к этому билету?",
        reply_markup=_image_choice_keyboard(),
    )


@router.callback_query(UploadTicket.waiting_for_image_choice, F.data == "upload:no_image")
async def choose_no_image(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin_callback(callback):
        await callback.answer("Нет доступа", show_alert=True)
        return

    await callback.answer()
    await _save_ticket_without_image(callback, state)


@router.callback_query(UploadTicket.waiting_for_image_choice, F.data == "upload:yes_image")
async def choose_yes_image(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin_callback(callback):
        await callback.answer("Нет доступа", show_alert=True)
        return

    await callback.answer()
    await state.set_state(UploadTicket.waiting_for_image)
    await callback.message.answer("Отправь картинку графика (как фото или файл PNG):")


@router.message(UploadTicket.waiting_for_image)
async def receive_ticket_image(message: Message, state: FSMContext) -> None:
    if await _deny_if_not_admin(message):
        await state.clear()
        return

    file_id = None
    if message.photo:
        file_id = message.photo[-1].file_id
    elif message.document and message.document.mime_type in {"image/png", "image/jpeg"}:
        file_id = message.document.file_id

    if file_id is None:
        await message.answer("Нужна картинка. Отправь фото или PNG-файл, или /cancel для отмены.")
        return

    data = await state.get_data()
    ticket_number = data["ticket_number"]
    image_path = _ticket_image_path(ticket_number)
    image_path.parent.mkdir(parents=True, exist_ok=True)

    await message.bot.download(file_id, destination=image_path)
    await upsert_ticket(
        ticket_id=ticket_number,
        title=data["title"],
        raw_text=data["raw_text"],
        has_image=True,
    )

    await state.clear()
    await message.answer(f"✅ Билет {ticket_number} сохранён с графиком.")
