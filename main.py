"""
Telegram Bot — точка входа.
Запуск aiogram бота в режиме polling или webhook на основе конфигурации в .env.
"""

import os
import asyncio
import logging
from urllib.parse import urlparse

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot import router

# ==========================================
# КОНФИГУРАЦИЯ
# ==========================================

load_dotenv()

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
USE_WEBHOOK: bool = os.getenv("USE_WEBHOOK", "false").lower() == "true"
WEBHOOK_URL: str = os.getenv("WEBHOOK_URL", "")
WEBHOOK_PORT: int = int(os.getenv("WEBHOOK_PORT", "8080"))

# Логирование
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ==========================================
# ЗАПУСК
# ==========================================

async def start_polling(bot: Bot, dp: Dispatcher) -> None:
    """Запускает бота в режиме long polling."""
    logger.info("Запуск бота в режиме POLLING...")
    await dp.start_polling(bot)


async def start_webhook(bot: Bot, dp: Dispatcher) -> None:
    """Запускает бота в режиме webhook через aiohttp."""
    from aiohttp import web
    from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

    logger.info(f"Запуск бота в режиме WEBHOOK: {WEBHOOK_URL}")
    await bot.set_webhook(WEBHOOK_URL)

    # Извлекаем путь из WEBHOOK_URL (например, /preservation-ppt-tgbot)
    webhook_path = urlparse(WEBHOOK_URL).path
    if not webhook_path or webhook_path == "/":
        webhook_path = "/webhook"

    app = web.Application()
    webhook_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    webhook_handler.register(app, path=webhook_path)
    setup_application(app, dp, bot=bot)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=WEBHOOK_PORT)
    await site.start()

    logger.info(f"Webhook-сервер запущен на порту {WEBHOOK_PORT}")
    # Держим сервер запущенным
    await asyncio.Event().wait()


async def main() -> None:
    """Инициализация бота и запуск."""
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN не задан в .env!")
        return

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.include_router(router)

    if USE_WEBHOOK:
        await start_webhook(bot, dp)
    else:
        await start_polling(bot, dp)


if __name__ == "__main__":
    asyncio.run(main())
