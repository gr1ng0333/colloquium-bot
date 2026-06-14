from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
import html as html_lib
from io import BytesIO
from pathlib import Path
import re
import time
from uuid import uuid4

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, User

from config import OWNER_ID, IMAGES_DIR, TOTAL_TICKETS
from database import add_admin, get_all_admin_ids, get_all_tickets_summary, remove_admin
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

STRANGER_TEXT = """🔒 Этот бот — приватный.

Заходит студент в бот за билетами... а бот ему:
«Доступ запрещён.»

— Но мне же экзамен сдавать!
— А мне — сервер оплачивать. У нас у всех проблемы.

Если тебе нужен доступ — попроси админа.
Узнай свой ID: /myid"""


def help_text(is_owner: bool) -> str:
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

    if is_owner:
        lines.extend(
            [
                "",
                "Команды владельца:",
                "/addadmin <id> — назначить админа",
                "/removeadmin <id> — снять админа",
                "/admins — список админов",
                "/cancel — отменить текущее действие",
            ]
        )

    return "\n".join(lines)


_admin_ids: set[int] = set()


async def load_admins() -> None:
    """Load admin IDs from the database into memory. Call at startup."""
    global _admin_ids
    _admin_ids = set(await get_all_admin_ids())


def is_owner_user(user: User | None) -> bool:
    return bool(user and user.id == OWNER_ID)


def is_admin_user(user: User | None) -> bool:
    return bool(user and (user.id == OWNER_ID or user.id in _admin_ids))


def is_admin_message(message: Message) -> bool:
    return is_admin_user(message.from_user)


def is_owner_message(message: Message) -> bool:
    return is_owner_user(message.from_user)


def _reply_keyboard(message: Message) -> "ReplyKeyboardMarkup":
    return main_keyboard(
        is_admin=is_admin_message(message),
        is_owner=is_owner_message(message),
    )


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
    document = message.document
    if document:
        is_plain_text = document.mime_type == "text/plain"
        is_txt_file = bool(
            document.file_name
            and document.file_name.lower().endswith((".txt", ".md"))
        )
        if is_plain_text or is_txt_file:
            buffer = BytesIO()
            await message.bot.download(document.file_id, destination=buffer)
            data = buffer.getvalue()
            try:
                return data.decode("utf-8-sig")
            except UnicodeDecodeError:
                return data.decode("utf-8", errors="replace")

    if message.text:
        return message.text

    return None


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
    await message.answer(text, reply_markup=_reply_keyboard(message))


async def send_long_message(message: Message, text: str) -> None:
    lines = text.splitlines()
    chunk = ""
    for line in lines:
        if len(line) > 3900:
            if chunk:
                await message.answer(chunk)
                chunk = ""
            for start in range(0, len(line), 3900):
                await message.answer(line[start : start + 3900])
            continue

        next_chunk = f"{chunk}\n{line}" if chunk else line
        if len(next_chunk) > 3900:
            await message.answer(chunk)
            chunk = line
        else:
            chunk = next_chunk

    if chunk:
        await message.answer(chunk)


async def send_raw_text_mono(message: Message, raw_text: str) -> None:
    """Send raw ticket text wrapped in <pre> HTML blocks.

    Splits into multiple messages when text exceeds Telegram limits.
    Uses HTML parse_mode to avoid Markdown escaping issues.
    """
    max_content_len = 4096 - len("<pre></pre>") - 50  # safety margin
    lines = raw_text.splitlines(keepends=True)
    chunks: list[str] = []
    current = ""

    for line in lines:
        escaped_line = html_lib.escape(line)
        if len(current) + len(escaped_line) > max_content_len:
            if current:
                chunks.append(current)
            current = escaped_line
        else:
            current += escaped_line

    if current:
        chunks.append(current)

    total = len(chunks)
    for i, chunk in enumerate(chunks, start=1):
        header = f"📄 Часть {i}/{total}\n" if total > 1 else ""
        await message.answer(f"{header}<pre>{chunk}</pre>", parse_mode="HTML")


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
    if not is_admin_message(message):
        await message.answer(STRANGER_TEXT)
        return
    await message.answer(START_TEXT, reply_markup=_reply_keyboard(message))


@router.message(Command("help"))
@router.message(F.text == HELP_BUTTON)
async def help_message(message: Message) -> None:
    if not is_admin_message(message):
        await message.answer(STRANGER_TEXT)
        return
    await message.answer(
        help_text(is_owner_message(message)),
        reply_markup=_reply_keyboard(message),
    )


@router.message(F.text == ALL_TICKETS_BUTTON)
async def all_tickets(message: Message) -> None:
    if not is_admin_message(message):
        return
    await send_long_message(message, await build_tickets_list_text(admin_status=False))


@router.message(Command("cancel"))
@router.message(F.text == CANCEL_BUTTON)
async def cancel(message: Message, state: FSMContext) -> None:
    if await state.get_state() is None:
        await message.answer("Нет активного действия.", reply_markup=_reply_keyboard(message))
        return

    await state.clear()
    await message.answer("Действие отменено.", reply_markup=_reply_keyboard(message))


@router.message(Command("myid"))
async def my_id(message: Message) -> None:
    user = message.from_user
    user_id = user.id if user else "unknown"
    is_admin = is_admin_message(message)
    is_owner = is_owner_user(message.from_user)
    if is_owner:
        status = "👑 Ты владелец бота"
    elif is_admin:
        status = "✅ Ты админ"
    else:
        status = "❌ Ты не админ"
    await message.answer(
        f"🆔 Твой Telegram ID: <code>{user_id}</code>\n{status}",
        parse_mode="HTML",
    )


@router.message(Command("addadmin"))
async def cmd_add_admin(message: Message) -> None:
    if not is_owner_user(message.from_user):
        await message.answer("⛔ Только владелец может назначать админов.")
        return

    args = (message.text or "").split()
    if len(args) < 2 or not args[1].isdigit():
        await message.answer("❓ Использование: /addadmin <user_id>")
        return

    new_id = int(args[1])
    if new_id == OWNER_ID:
        await message.answer("Ты уже владелец, не нужно добавлять себя.")
        return

    added = await add_admin(new_id)
    if added:
        _admin_ids.add(new_id)
        await message.answer(f"✅ Пользователь <code>{new_id}</code> назначен админом.", parse_mode="HTML")
    else:
        await message.answer(f"⚠️ Пользователь <code>{new_id}</code> уже админ.", parse_mode="HTML")


@router.message(Command("removeadmin"))
async def cmd_remove_admin(message: Message) -> None:
    if not is_owner_user(message.from_user):
        await message.answer("⛔ Только владелец может удалять админов.")
        return

    args = (message.text or "").split()
    if len(args) < 2 or not args[1].isdigit():
        await message.answer("❓ Использование: /removeadmin <user_id>")
        return

    target_id = int(args[1])
    removed = await remove_admin(target_id)
    if removed:
        _admin_ids.discard(target_id)
        await message.answer(f"✅ Пользователь <code>{target_id}</code> больше не админ.", parse_mode="HTML")
    else:
        await message.answer(f"⚠️ Пользователь <code>{target_id}</code> не найден среди админов.", parse_mode="HTML")


@router.message(Command("admins"))
async def cmd_list_admins(message: Message) -> None:
    if not is_admin_message(message):
        return

    lines = [f"👑 Владелец: <code>{OWNER_ID}</code>"]
    if _admin_ids:
        for aid in sorted(_admin_ids):
            lines.append(f"✅ Админ: <code>{aid}</code>")
    else:
        lines.append("Нет дополнительных админов.")

    await message.answer("\n".join(lines), parse_mode="HTML")
