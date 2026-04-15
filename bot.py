import asyncio
import logging

from aiogram import Bot, Dispatcher

from app.config import load_config
from app.db import Database
from app.handlers import setup_routers

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    config = load_config()
    db = Database(config.db_dsn)
    bot = Bot(token=config.bot_token)
    dp = Dispatcher()

    dp["config"] = config
    dp["db"] = db

    setup_routers(dp)

    logger.info("Bot started")
    try:
        await dp.start_polling(bot)
    finally:
        db.close()
        logger.info("Bot stopped")


if __name__ == "__main__":
    asyncio.run(main())
