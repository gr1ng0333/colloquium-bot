import asyncio

from aiogram import Bot, Dispatcher

from config import BOT_TOKEN
from database import init_db
from handlers import get_tickets, upload_ticket


async def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set. Add it to .env before starting the bot.")

    await init_db()
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(upload_ticket.router)
    dp.include_router(get_tickets.router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
