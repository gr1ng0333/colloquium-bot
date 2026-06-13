import asyncio
import logging

from aiogram import Bot, Dispatcher

from config import BOT_TOKEN
from database import init_db
from handlers import (
    admin_menu,
    common,
    delete_ticket,
    edit_ticket,
    get_tickets,
    manage_image,
    upload_ticket,
)


async def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set. Add it to .env before starting the bot.")

    from config import ADMIN_ID
    if ADMIN_ID == 0:
        logging.warning("ADMIN_ID is not set! Admin functions will be disabled for everyone.")
    else:
        logging.info(f"Bot starting with ADMIN_ID={ADMIN_ID}")

    await init_db()
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(common.router)
    dp.include_router(admin_menu.router)
    dp.include_router(upload_ticket.router)
    dp.include_router(edit_ticket.router)
    dp.include_router(manage_image.router)
    dp.include_router(delete_ticket.router)
    dp.include_router(get_tickets.router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
