from __future__ import annotations

import aiosqlite

from config import DB_PATH


CREATE_TICKETS_TABLE = """
CREATE TABLE IF NOT EXISTS tickets (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    raw_text TEXT NOT NULL,
    has_image INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


def _row_to_dict(row: aiosqlite.Row) -> dict:
    return {
        "id": row["id"],
        "title": row["title"],
        "raw_text": row["raw_text"],
        "has_image": bool(row["has_image"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(CREATE_TICKETS_TABLE)
        await db.commit()


async def get_ticket(ticket_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
        row = await cursor.fetchone()
        await cursor.close()

    return _row_to_dict(row) if row else None


async def get_tickets(ticket_ids: list[int]) -> list[dict]:
    if not ticket_ids:
        return []

    tickets = []
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        for ticket_id in ticket_ids:
            cursor = await db.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
            row = await cursor.fetchone()
            await cursor.close()
            if row:
                tickets.append(_row_to_dict(row))

    return tickets


async def upsert_ticket(
    ticket_id: int,
    title: str,
    raw_text: str,
    has_image: bool,
) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO tickets (id, title, raw_text, has_image, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO UPDATE SET
                title = excluded.title,
                raw_text = excluded.raw_text,
                has_image = excluded.has_image,
                updated_at = CURRENT_TIMESTAMP
            """,
            (ticket_id, title, raw_text, int(has_image)),
        )
        await db.commit()


async def delete_ticket(ticket_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("DELETE FROM tickets WHERE id = ?", (ticket_id,))
        deleted = cursor.rowcount > 0
        await cursor.close()
        await db.commit()

    return deleted


async def get_all_ticket_ids() -> list[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT id FROM tickets ORDER BY id")
        rows = await cursor.fetchall()
        await cursor.close()

    return [row[0] for row in rows]


async def get_ticket_count() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM tickets")
        row = await cursor.fetchone()
        await cursor.close()

    return int(row[0])


async def get_all_tickets_summary() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, title, has_image FROM tickets ORDER BY id"
        )
        rows = await cursor.fetchall()
        await cursor.close()

    return [
        {
            "id": row["id"],
            "title": row["title"],
            "has_image": bool(row["has_image"]),
        }
        for row in rows
    ]


async def update_ticket_text(ticket_id: int, title: str, raw_text: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE tickets
            SET title = ?, raw_text = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (title, raw_text, ticket_id),
        )
        await db.commit()


async def update_ticket_image(ticket_id: int, has_image: bool) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE tickets
            SET has_image = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (int(has_image), ticket_id),
        )
        await db.commit()
