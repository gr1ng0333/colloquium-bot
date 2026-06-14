"""Batch cluster upload handler.

Parses a cluster text containing multiple tickets separated by bold numbered
headers (e.g. ``**1. Ticket title**``) and graph placeholders
(``[ГРАФИК]...[/ГРАФИК]``).  Saves all tickets to the database and then
sequentially prompts the admin for each graph image.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from database import get_ticket, update_ticket_image, upsert_ticket
from handlers.common import (
    extract_title,
    is_owner_user,
    read_text_from_message,
    ticket_image_path,
)
from keyboards import (
    cancel_keyboard,
    cluster_skip_image_inline,
    main_keyboard,
)
from states import UploadCluster


router = Router()


# ── Cluster parser ──────────────────────────────────────────────────


@dataclass
class GraphPlaceholder:
    """Describes one [ГРАФИК]...[/ГРАФИК] block inside a ticket."""

    source: str  # "Источник: ..."
    description: str  # "Что изображено: ..."
    image_index: int = 1  # 1-based index within the ticket


@dataclass
class ClusterTicket:
    """One ticket extracted from a cluster text."""

    number: int
    title: str
    raw_text: str  # with [ГРАФИК] blocks REMOVED
    graphs: list[GraphPlaceholder] = field(default_factory=list)


_TICKET_HEADER_RE = re.compile(
    r"^\*\*(\d+)\.\s+(.+?)\*\*\s*$",
    re.MULTILINE,
)
_GRAPH_BLOCK_RE = re.compile(
    r"\[ГРАФИК\]\s*\r?\n(.*?)\[/ГРАФИК\]",
    re.DOTALL,
)
_SOURCE_RE = re.compile(r"Источник:\s*(.+)")
_DESCR_RE = re.compile(r"Что изображено:\s*(.+)")


def _parse_graphs(text: str) -> tuple[str, list[GraphPlaceholder]]:
    """Extract all [ГРАФИК] blocks and return cleaned text + graph list."""
    graphs: list[GraphPlaceholder] = []
    idx = 0

    def _replace(match: re.Match) -> str:
        nonlocal idx
        idx += 1
        body = match.group(1)
        source_m = _SOURCE_RE.search(body)
        descr_m = _DESCR_RE.search(body)
        graphs.append(
            GraphPlaceholder(
                source=source_m.group(1).strip() if source_m else "—",
                description=descr_m.group(1).strip() if descr_m else "—",
                image_index=idx,
            )
        )
        return ""

    cleaned = _GRAPH_BLOCK_RE.sub(_replace, text)
    # collapse runs of 3+ blank lines to 2
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip(), graphs


def parse_cluster(text: str) -> list[ClusterTicket]:
    """Split raw cluster text into individual tickets."""
    headers = list(_TICKET_HEADER_RE.finditer(text))
    if not headers:
        return []

    tickets: list[ClusterTicket] = []
    for i, match in enumerate(headers):
        number = int(match.group(1))
        # raw text: from start of this header to start of the next one
        start = match.start()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        raw_section = text[start:end].strip()
        cleaned, graphs = _parse_graphs(raw_section)
        tickets.append(
            ClusterTicket(
                number=number,
                title=extract_title(cleaned),
                raw_text=cleaned,
                graphs=graphs,
            )
        )
    return tickets


# ── FSM flow ────────────────────────────────────────────────────────


@router.callback_query(F.data == "admin_cluster")
async def start_cluster_upload(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_owner_user(callback.from_user):
        await callback.answer("Нет доступа", show_alert=True)
        return

    await state.clear()
    await state.set_state(UploadCluster.waiting_for_text)
    await callback.answer()
    await callback.message.answer(
        "📦 Отправь текст кластера (весь текст одним сообщением "
        "или .txt файлом).\n\n"
        "Бот найдёт все билеты по заголовкам вида **N. Название** "
        "и все плейсхолдеры [ГРАФИК].",
        reply_markup=cancel_keyboard(),
    )


@router.message(UploadCluster.waiting_for_text)
async def receive_cluster_text(message: Message, state: FSMContext) -> None:
    raw_text = await read_text_from_message(message)
    if not raw_text:
        await message.answer("Отправь текст или .txt файл с кластером.")
        return

    tickets = parse_cluster(raw_text)
    if not tickets:
        await message.answer(
            "❌ Не удалось найти билеты в тексте.\n"
            "Убедись, что билеты начинаются с заголовка **N. Название**"
        )
        return

    # Save all tickets to the database
    saved_count = 0
    overwritten: list[int] = []
    for t in tickets:
        existing = await get_ticket(t.number)
        if existing:
            overwritten.append(t.number)
        await upsert_ticket(t.number, t.title, t.raw_text, has_image=False)
        saved_count += 1

    # Collect all graphs across all tickets into a flat queue
    graph_queue: list[dict] = []
    for t in tickets:
        for g in t.graphs:
            graph_queue.append(
                {
                    "ticket_number": t.number,
                    "source": g.source,
                    "description": g.description,
                    "image_index": g.image_index,
                }
            )

    total_graphs = len(graph_queue)

    # Build summary
    nums = ", ".join(str(t.number) for t in tickets)
    summary = f"✅ Загружено {saved_count} билетов: {nums}\n"
    if overwritten:
        ow = ", ".join(str(n) for n in overwritten)
        summary += f"🔄 Перезаписаны: {ow}\n"
    summary += f"📊 Найдено графиков: {total_graphs}"

    if not graph_queue:
        # No graphs — done!
        await state.clear()
        await message.answer(
            summary + "\n\n✅ Загрузка кластера завершена!",
            reply_markup=main_keyboard(is_admin=True, is_owner=True),
        )
        return

    # Store graph queue in state and start asking
    await state.update_data(
        graph_queue=graph_queue,
        graph_index=0,
        total_graphs=total_graphs,
    )
    await message.answer(summary)
    await _ask_next_graph(message, state)


async def _ask_next_graph(message: Message, state: FSMContext) -> None:
    """Ask admin for the next graph image in the queue."""
    data = await state.get_data()
    idx = data["graph_index"]
    queue: list[dict] = data["graph_queue"]

    if idx >= len(queue):
        # All graphs done
        await state.clear()
        await message.answer(
            "✅ Все графики загружены! Кластер полностью обработан.",
            reply_markup=main_keyboard(is_admin=True, is_owner=True),
        )
        return

    g = queue[idx]
    total = data["total_graphs"]
    await state.set_state(UploadCluster.waiting_for_image)
    await message.answer(
        f"📊 График {idx + 1}/{total}\n"
        f"📝 Билет #{g['ticket_number']}, график #{g['image_index']}\n\n"
        f"📍 Источник: {g['source']}\n"
        f"🖼 Что изображено: {g['description']}\n\n"
        "Отправь фото/картинку или нажми ⏭ Пропустить.",
        reply_markup=cluster_skip_image_inline(),
    )


@router.callback_query(UploadCluster.waiting_for_image, F.data == "cluster_skip_img")
async def skip_cluster_image(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_owner_user(callback.from_user):
        await callback.answer("Нет доступа", show_alert=True)
        return

    data = await state.get_data()
    idx = data["graph_index"]
    queue: list[dict] = data["graph_queue"]
    g = queue[idx]

    await callback.answer(
        f"Пропущен график #{g['image_index']} билета #{g['ticket_number']}"
    )
    await state.update_data(graph_index=idx + 1)
    await _ask_next_graph(callback.message, state)


@router.message(UploadCluster.waiting_for_image)
async def receive_cluster_image(message: Message, state: FSMContext) -> None:
    # Accept photo or document-image
    file_id = None
    if message.photo:
        file_id = message.photo[-1].file_id
    elif message.document and message.document.mime_type and message.document.mime_type.startswith("image/"):
        file_id = message.document.file_id

    if not file_id:
        await message.answer("Нужно отправить фото или картинку (или нажми ⏭ Пропустить).")
        return

    data = await state.get_data()
    idx = data["graph_index"]
    queue: list[dict] = data["graph_queue"]
    g = queue[idx]

    # Download and save the image
    dest = ticket_image_path(g["ticket_number"], g["image_index"])
    dest.parent.mkdir(parents=True, exist_ok=True)
    await message.bot.download(file_id, destination=str(dest))

    # Mark ticket as having images in the DB
    await update_ticket_image(g["ticket_number"], has_image=True)

    await message.answer(
        f"✅ График #{g['image_index']} для билета #{g['ticket_number']} сохранён."
    )
    await state.update_data(graph_index=idx + 1)
    await _ask_next_graph(message, state)

