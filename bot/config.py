"""Настройки бота: секреты из .env (вне Git), прайс и часы — здесь."""

import os
from pathlib import Path

from dotenv import load_dotenv

# .env ищется рядом с config.py — работает и локально, и на сервере
load_dotenv(Path(__file__).resolve().parent / ".env")

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    raise SystemExit(
        "ОШИБКА: BOT_TOKEN не найден.\n"
        "Скопируйте .env.example в .env (рядом с config.py) и впишите "
        "BOT_TOKEN из @BotFather.\n"
        "На сервере можно задать переменную окружения BOT_TOKEN в настройках."
    )

# Telegram ID администраторов (мастера) — через запятую. Узнать: @userinfobot
ADMIN_IDS = {
    int(x) for x in os.getenv("ADMIN_IDS", "").replace(" ", "").split(",") if x
}

MASTER_NAME = "Анастасия"
MASTER_CONTACT = "@kkkarta" # Telegram-никнейм мастера, чтобы клиенты могли написать ему напрямую

# Прайс: название услуги -> цена в рублях
PRICES = {
    "Маникюр без покрытия": 1500,
    "Маникюр + покрытие гель-лак": 2500,
    "Наращивание ногтей": 4000,
    "Снятие покрытия": 500,
    "Дизайн 2 ногтей": 300,
    "Ремонт ногтя": 300,
}

# Рабочие часы и длительность одного слота (в часах)
WORK_START_HOUR = 10
WORK_END_HOUR = 19
SLOT_HOURS = 2

# На сколько дней вперёд можно записаться (28 = полный месяц, сетка 7×4)
MAX_DAYS_AHEAD = 28

# Путь к базе данных
DB_PATH = "bookings.db"

# Прокси для доступа к Telegram API (нужен в РФ при запуске с локального ПК).
# На сервере за границей не нужен. Задаётся в .env или переменной окружения.
# Пример: socks5://127.0.0.1:10808 или http://127.0.0.1:8888
PROXY_URL = os.getenv("PROXY_URL", "").strip() or None
