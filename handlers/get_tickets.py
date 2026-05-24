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


@router.message(StateFilter(None), F.text)
async def handle_get_tickets(message: Message) -> None:
    numbers = extract_ticket_numbers(message.text or "")
    if not numbers:
        return

    found_tickets = await get_tickets(numbers)
    found_ids = [ticket["id"] for ticket in found_tickets]
    missing_ids = [ticket_id for ticket_id in numbers if ticket_id not in found_ids]

    found_text = ", ".join(map(str, found_ids)) if found_ids else "нет"
    status_lines = [f"Найдены билеты: {found_text}"]
    if missing_ids:
        status_lines.append(f"Не найдены: {', '.join(map(str, missing_ids))}")
    await message.answer("\n".join(status_lines))

    if not found_tickets:
        return

    html_path = await render_tickets(found_tickets)
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
    finally:
        if os.path.exists(html_path):
            os.remove(html_path)
