from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from io import BytesIO
from pathlib import Path
import re
import time
from uuid import uuid4

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, User

from config import ADMIN_ID, IMAGES_DIR, TOTAL_TICKETS
from database import get_all_tickets_summary
from keyboards import (
    ALL_TICKETS_BUTTON,
    CANCEL_BUTTON,
    HELP_BUTTON,
    main_keyboard,
)


router = Router()

TEXT_COLLECTION_DELAY = 1.5
TEXT_COLLECTION_IDLE_SECONDS = 1.4
MAX_TEXT_PARTS = 3
MAX_TICKET_IMAGES = 5
TextFinalizer = Callable[[Message, FSMContext, str, int], Awaitable[None]]

START_TEXT = """📚 Билеты к коллоквиуму №2

Отправь номера билетов, и я соберу их в один файл.

Примеры:
• 1, 22, 7
• 5 12 28
• 22"""


def help_text(is_admin: bool) -> str:
    lines = [
        "Как пользоваться:",
        "",
        "Отправь номера билетов любым удобным способом:",
        "1, 22, 7 — через запятую",
        "5 12 28 — через пробел",
        "22 — один билет",
        "",
        "Я соберу их в один HTML-файл с тёмной темой, который удобно",
        "читать на телефоне. Формулы отображаются через KaTeX —",
        "нужен интернет при первом открытии.",
        "",
        "Если к билету есть график — пришлю его отдельной картинкой.",
    ]

    if is_admin:
        lines.extend(
            [
                "",
                "Команды администратора:",
                "/upload — загрузить или обновить билет",
                "/status — посмотреть, сколько билетов загружено",
                "/delete 22 — удалить билет по номеру",
                "/cancel — отменить текущее действие",
            ]
        )

    return "\n".join(lines)


def is_admin_user(user: User | None) -> bool:
    return bool(user and user.id == ADMIN_ID)


def is_admin_message(message: Message) -> bool:
    return is_admin_user(message.from_user)


def parse_ticket_number(text: str | None) -> int | None:
    if not text:
        return None

    match = re.search(r"\d+", text)
    if not match:
        return None

    number = int(match.group(0))
    if 1 <= number <= TOTAL_TICKETS:
        return number

    return None


def extract_title(raw_text: str) -> str:
    for line in raw_text.splitlines():
        title = line.strip()
        if title:
            return title.replace("**", "")[:200]

    return "Без названия"


def short_title(title: str, limit: int = 50) -> str:
    title = title.strip().replace("\n", " ")
    if len(title) <= limit:
        return title
    return f"{title[: limit - 1]}…"


def ticket_image_path(ticket_id: int, image_index: int = 1) -> Path:
    if image_index == 1:
        return Path(IMAGES_DIR) / f"ticket_{ticket_id}.png"
    return Path(IMAGES_DIR) / f"ticket_{ticket_id}_{image_index}.png"


def ticket_image_paths(ticket_id: int) -> list[Path]:
    return [
        ticket_image_path(ticket_id, image_index)
        for image_index in range(1, MAX_TICKET_IMAGES + 1)
        if ticket_image_path(ticket_id, image_index).exists()
    ]


def ticket_image_count(ticket_id: int) -> int:
    return len(ticket_image_paths(ticket_id))


def next_ticket_image_index(ticket_id: int) -> int | None:
    for image_index in range(1, MAX_TICKET_IMAGES + 1):
        if not ticket_image_path(ticket_id, image_index).exists():
            return image_index
    return None


def delete_ticket_images(ticket_id: int) -> None:
    for image_index in range(1, MAX_TICKET_IMAGES + 1):
        image_path = ticket_image_path(ticket_id, image_index)
        if image_path.exists():
            image_path.unlink()


def delete_all_ticket_images() -> None:
    images_dir = Path(IMAGES_DIR)
    if not images_dir.exists():
        return
    for image_file in images_dir.glob("ticket_*.png"):
        image_file.unlink()


async def read_text_from_message(message: Message) -> str | None:
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


async def _reset_text_collection(state: FSMContext) -> None:
    await state.update_data(
        text_collecting=False,
        text_collection_id=None,
        text_part_count=0,
        last_message_time=0.0,
    )


async def _finalize_text_after_idle(
    message: Message,
    state: FSMContext,
    expected_state: str,
    collection_id: str,
    finalize: TextFinalizer,
) -> None:
    await asyncio.sleep(TEXT_COLLECTION_DELAY)

    while True:
        if await state.get_state() != expected_state:
            return

        data = await state.get_data()
        if (
            not data.get("text_collecting")
            or data.get("text_collection_id") != collection_id
        ):
            return

        last_message_time = float(data.get("last_message_time") or 0)
        idle_time = time.time() - last_message_time
        if idle_time < TEXT_COLLECTION_IDLE_SECONDS:
            await asyncio.sleep(TEXT_COLLECTION_IDLE_SECONDS - idle_time)
            continue

        raw_text = data.get("raw_text")
        if not raw_text:
            await _reset_text_collection(state)
            return

        part_count = int(data.get("text_part_count") or 1)
        await _reset_text_collection(state)
        await finalize(message, state, raw_text, part_count)
        return


async def collect_text_or_document(
    message: Message,
    state: FSMContext,
    expected_state: str,
    finalize: TextFinalizer,
) -> bool:
    if message.document:
        raw_text = await read_text_from_message(message)
        if raw_text is None:
            return False

        await _reset_text_collection(state)
        await finalize(message, state, raw_text, 1)
        return True

    if not message.text:
        return False

    data = await state.get_data()
    if data.get("text_collecting"):
        part_count = int(data.get("text_part_count") or 1)
        if part_count >= MAX_TEXT_PARTS:
            await _reset_text_collection(state)
            await state.update_data(raw_text=None)
            await message.answer(
                "Текст пришёл больше чем 3 сообщениями. Отправь билет .txt файлом, пожалуйста."
            )
            return True

        raw_text = data.get("raw_text") or ""
        await state.update_data(
            raw_text=f"{raw_text}\n{message.text}",
            text_part_count=part_count + 1,
            last_message_time=time.time(),
        )
        return True

    collection_id = uuid4().hex
    await state.update_data(
        raw_text=message.text,
        text_collecting=True,
        text_collection_id=collection_id,
        text_part_count=1,
        last_message_time=time.time(),
    )
    asyncio.create_task(
        _finalize_text_after_idle(
            message=message,
            state=state,
            expected_state=expected_state,
            collection_id=collection_id,
            finalize=finalize,
        )
    )
    return True


async def finish_fsm(message: Message, text: str) -> None:
    await message.answer(text, reply_markup=main_keyboard(is_admin_message(message)))


async def send_long_message(message: Message, text: str) -> None:
    lines = text.splitlines()
    chunk = ""
    for line in lines:
        next_chunk = f"{chunk}\n{line}" if chunk else line
        if len(next_chunk) > 3900:
            await message.answer(chunk)
            chunk = line
        else:
            chunk = next_chunk

    if chunk:
        await message.answer(chunk)


async def build_tickets_list_text(admin_status: bool = False) -> str:
    summaries = {ticket["id"]: ticket for ticket in await get_all_tickets_summary()}
    loaded_count = len(summaries)
    image_count = sum(1 for ticket in summaries.values() if ticket["has_image"])

    lines = ["📋 Статус загрузки:" if admin_status else "📋 Список билетов:", ""]
    for ticket_id in range(1, TOTAL_TICKETS + 1):
        ticket = summaries.get(ticket_id)
        if ticket:
            actual_image_count = ticket_image_count(ticket_id)
            image_mark = f" 📊×{actual_image_count}" if actual_image_count > 1 else " 📊" if actual_image_count else ""
            lines.append(f"✅ {ticket_id}. {ticket['title']}{image_mark}")
        else:
            lines.append(f"❌ {ticket_id}. Билет не загружен")

    lines.append("")
    if admin_status:
        lines.append(
            f"Загружено: {loaded_count} / {TOTAL_TICKETS} "
            f"(из них {image_count} с графиками)"
        )
    else:
        lines.append("📊 — есть график")
        lines.append("")
        lines.append(f"Загружено: {loaded_count} / {TOTAL_TICKETS}")
        lines.append("Отправь номера нужных билетов.")

    return "\n".join(lines)


@router.message(Command("start"))
async def start(message: Message) -> None:
    await message.answer(
        START_TEXT,
        reply_markup=main_keyboard(is_admin_message(message)),
    )


@router.message(Command("help"))
@router.message(F.text == HELP_BUTTON)
async def help_message(message: Message) -> None:
    await message.answer(
        help_text(is_admin_message(message)),
        reply_markup=main_keyboard(is_admin_message(message)),
    )


@router.message(F.text == ALL_TICKETS_BUTTON)
async def all_tickets(message: Message) -> None:
    await send_long_message(message, await build_tickets_list_text(admin_status=False))


@router.message(Command("cancel"))
@router.message(F.text == CANCEL_BUTTON)
async def cancel(message: Message, state: FSMContext) -> None:
    if await state.get_state() is None:
        await message.answer(
            "Нет активного действия.",
            reply_markup=main_keyboard(is_admin_message(message)),
        )
        return

    await state.clear()
    await message.answer(
        "Действие отменено.",
        reply_markup=main_keyboard(is_admin_message(message)),
    )
