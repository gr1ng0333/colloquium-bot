from __future__ import annotations

import os
import re
from pathlib import Path

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.types import BufferedInputFile, FSInputFile, Message

from config import IMAGES_DIR, TOTAL_TICKETS
from database import get_tickets
from renderer import render_tickets


router = Router()


def extract_ticket_numbers(text: str) -> list[int]:
    numbers = [int(n) for n in re.findall(r"\d+", text)]
    valid = [n for n in numbers if 1 <= n <= TOTAL_TICKETS]

    seen = set()
    result = []
    for number in valid:
        if number not in seen:
            seen.add(number)
            result.append(number)

    return result


def _document_filename(ticket_ids: list[int]) -> str:
    if len(ticket_ids) == 1:
        return f"ticket_{ticket_ids[0]}.html"
    return "tickets.html"


def _numbers_text(ticket_ids: list[int]) -> str:
    return ", ".join(map(str, ticket_ids))


@router.message(StateFilter(None), F.text)
async def handle_get_tickets(message: Message) -> None:
    numbers = extract_ticket_numbers(message.text or "")
    if not numbers:
        return

    found_tickets = await get_tickets(numbers)
    found_ids = [ticket["id"] for ticket in found_tickets]
    missing_ids = [ticket_id for ticket_id in numbers if ticket_id not in found_ids]

    if not found_tickets:
        await message.answer(f"⚠️ Не загружены: {_numbers_text(missing_ids)}")
        return

    await message.answer(f"⏳ Собираю билеты {_numbers_text(found_ids)}...")

    html_path = await render_tickets(found_tickets)
    sent_image_ids: list[int] = []
    try:
        filename = _document_filename(found_ids)
        document_bytes = Path(html_path).read_bytes()
        await message.bot.send_document(
            chat_id=message.chat.id,
            document=BufferedInputFile(document_bytes, filename=filename),
        )

        for ticket in found_tickets:
            if not ticket["has_image"]:
                continue

            image_path = Path(IMAGES_DIR) / f"ticket_{ticket['id']}.png"
            if image_path.exists():
                await message.bot.send_document(
                    chat_id=message.chat.id,
                    document=FSInputFile(image_path),
                    caption=f"📊 К вопросу {ticket['id']}",
                )
                sent_image_ids.append(ticket["id"])
    finally:
        if os.path.exists(html_path):
            os.remove(html_path)

    summary_lines = [f"✅ Готово: билеты {_numbers_text(found_ids)}"]
    if missing_ids:
        summary_lines.append(f"⚠️ Не загружены: {_numbers_text(missing_ids)}")

    if sent_image_ids:
        summary_lines.append(f"📊 Графики: к вопросам {_numbers_text(sent_image_ids)}")
    else:
        summary_lines.append("📊 Графики: нет")

    await message.answer("\n".join(summary_lines))
