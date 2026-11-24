"""Точка входа: запуск бота Telegram на aiogram 3."""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramNetworkError
from aiogram.types import BotCommand

import database as db
from config import BOT_TOKEN, PROXY_URL
from fsm_storage import SQLiteStorage
from handlers import router

COMMANDS = [
    BotCommand(command="start", description="Начать запись"),
    BotCommand(command="help", description="Прайс-лист"),
    BotCommand(command="cancel", description="Отменить запись"),
    BotCommand(command="bookings", description="Записи на сегодня (мастер)"),
    BotCommand(command="all", description="Все записи (мастер)"),
]


def make_bot() -> Bot:
    session = AiohttpSession(proxy=PROXY_URL) if PROXY_URL else None
    return Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        session=session,
    )


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    if PROXY_URL:
        logging.info("Использую прокси: %s", PROXY_URL)

    db.init_db()

    dp = Dispatcher(storage=SQLiteStorage())
    dp.include_router(router)

    attempt = 0
    while True:
        bot = make_bot()
        try:
            try:
                await bot.set_my_commands(COMMANDS)
                await bot.delete_webhook(drop_pending_updates=True)
            except TelegramNetworkError as e:
                # команды/вебхук не критичны — polling всё равно поднимется сам
                logging.warning("Первичный запрос к Telegram не прошёл: %s", e)
            attempt = 0
            await dp.start_polling(bot)
            break  # корректная остановка (сигнал) — выходим
        except (TelegramNetworkError, OSError) as e:
            attempt += 1
            delay = min(60, 5 * attempt)
            logging.warning(
                "Нет связи с Telegram (%s). Повтор через %d с. "
                "Включите VPN/прокси или пропишите PROXY_URL в config.py.",
                e, delay,
            )
            await asyncio.sleep(delay)
        finally:
            await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Бот остановлен.")
