from __future__ import annotations

import os
import re
from pathlib import Path

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.types import BufferedInputFile, FSInputFile, Message

from config import TOTAL_TICKETS
from database import get_tickets
from handlers.common import is_admin_message, ticket_image_paths
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
    if not is_admin_message(message):
        return

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
    sent_image_counts: dict[int, int] = {}
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

            image_paths = ticket_image_paths(ticket["id"])
            for image_index, image_path in enumerate(image_paths, start=1):
                await message.bot.send_document(
                    chat_id=message.chat.id,
                    document=FSInputFile(image_path),
                    caption=f"📊 К вопросу {ticket['id']} (график {image_index})",
                )
            if image_paths:
                sent_image_counts[ticket["id"]] = len(image_paths)
    finally:
        if os.path.exists(html_path):
            os.remove(html_path)

    summary_lines = [f"✅ Готово: билеты {_numbers_text(found_ids)}"]
    if missing_ids:
        summary_lines.append(f"⚠️ Не загружены: {_numbers_text(missing_ids)}")

    if sent_image_counts:
        image_summary = ", ".join(
            f"{ticket_id} ({count})"
            for ticket_id, count in sent_image_counts.items()
        )
        summary_lines.append(f"📊 Графики: к вопросам {image_summary}")
    else:
        summary_lines.append("📊 Графики: нет")

    await message.answer("\n".join(summary_lines))
