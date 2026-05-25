from __future__ import annotations

from io import BytesIO
from pathlib import Path
import re

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


def ticket_image_path(ticket_id: int) -> Path:
    return Path(IMAGES_DIR) / f"ticket_{ticket_id}.png"


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
            image_mark = " 📊" if ticket["has_image"] else ""
            lines.append(f"✅ {ticket_id}. {short_title(ticket['title'])}{image_mark}")
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
