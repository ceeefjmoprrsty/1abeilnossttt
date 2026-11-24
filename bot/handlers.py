"""Обработчики: вся запись идёт в ОДНО сообщение, которое обновляется на каждом шаге."""

import re
from datetime import date, datetime, timedelta

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    ReplyKeyboardRemove,
)

import database as db
from config import (
    ADMIN_IDS,
    MAX_DAYS_AHEAD,
    MASTER_CONTACT,
    MASTER_NAME,
    PRICES,
    SLOT_HOURS,
    WORK_END_HOUR,
    WORK_START_HOUR,
)
from states import BookingStates

router = Router()

# ---------- Утилиты ----------

MONTHS = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]
WEEKDAYS_FULL = [
    "понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье",
]
WEEKDAYS_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

PHONE_RE = re.compile(r"^(?:\+7|8)[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}$")

CANCEL_TEXT = "❌ Отмена"


def fmt_date(d: date) -> str:
    return f"{d.day} {MONTHS[d.month - 1]}, {WEEKDAYS_FULL[d.weekday()]}"


def parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def normalize_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone)
    if digits.startswith("8"):
        digits = "7" + digits[1:]
    return f"+{digits[0]} {digits[1:4]} {digits[4:7]}-{digits[7:9]}-{digits[9:11]}"


def all_slots() -> list[str]:
    return [f"{h:02d}:00" for h in range(WORK_START_HOUR, WORK_END_HOUR, SLOT_HOURS)]


# ---------- Клавиатуры ----------

def _cancel_row() -> list[InlineKeyboardButton]:
    return [InlineKeyboardButton(text=CANCEL_TEXT, callback_data="cancel")]


def services_kb() -> InlineKeyboardMarkup:
    rows, row = [], []
    for idx, (name, price) in enumerate(PRICES.items()):
        row.append(InlineKeyboardButton(text=f"{name} {price}₽", callback_data=f"svc:{idx}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append(_cancel_row())
    return InlineKeyboardMarkup(inline_keyboard=rows)


def calendar_kb() -> InlineKeyboardMarkup:
    """Сетка 7 колонок (Пн–Вс) на 4+ строк. На кнопках только число."""
    tomorrow = date.today() + timedelta(days=1)
    last_day = date.today() + timedelta(days=MAX_DAYS_AHEAD)
    free = free_dates(tomorrow, last_day)

    start = tomorrow - timedelta(days=tomorrow.weekday())  # понедельник недели завтрашнего дня
    # Telegram не допускает inline-кнопки без callback_data — у заголовка «глушитель»
    rows = [[InlineKeyboardButton(text=w, callback_data="wd") for w in WEEKDAYS_SHORT]]
    d = start
    while d <= last_day:
        row = []
        for _ in range(7):
            if tomorrow <= d <= last_day and d.isoformat() in free:
                row.append(
                    InlineKeyboardButton(text=f"{d.day}", callback_data=f"date:{d.isoformat()}")
                )
            else:
                row.append(InlineKeyboardButton(text="·", callback_data="off"))
            d += timedelta(days=1)
        rows.append(row)
    rows.append(_cancel_row())
    return InlineKeyboardMarkup(inline_keyboard=rows)


def free_dates(first: date, last: date) -> set[str]:
    """Даты, на которые остались свободные слоты."""
    total = len(all_slots())
    booked = db.get_booked_counts(first.isoformat(), last.isoformat())
    return {
        d.isoformat()
        for d in (first + timedelta(days=i) for i in range((last - first).days + 1))
        if booked.get(d.isoformat(), 0) < total
    }


def times_kb(date_iso: str) -> InlineKeyboardMarkup:
    rows, row = [], []
    for slot in db.get_available_slots(date_iso):
        row.append(InlineKeyboardButton(text=slot, callback_data=f"time:{slot}"))
        if len(row) == 4:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append(_cancel_row())
    return InlineKeyboardMarkup(inline_keyboard=rows)


def only_cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[_cancel_row()])


def confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm"),
                InlineKeyboardButton(text=CANCEL_TEXT, callback_data="cancel"),
            ]
        ]
    )


NO_KB = ReplyKeyboardRemove()


def start_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="💅 Записаться", callback_data="book")]]
    )


# ---------- Карточка (единое сообщение) ----------

def render_card(data: dict, hint: str) -> str:
    """Текст карточки: все ответы клиента в одном сообщении."""
    def val(key: str, filled: str) -> str:
        return f"{filled} ✅" if data.get(key) else "—"

    service = val("service", f"{data.get('service')} — {data.get('price')} ₽")
    day = val("date", fmt_date(parse_date(data["date"]))) if data.get("date") else "—"
    lines = [
        f"💅 Запись к мастеру {MASTER_NAME} ({MASTER_CONTACT})",
        "",
        f"1. Услуга:  {service}",
        f"2. Дата:    {day}",
        f"3. Время:   {val('time', str(data.get('time')))}",
        f"4. Имя:     {val('name', str(data.get('name')))}",
        f"5. Телефон: {val('phone', str(data.get('phone')))}",
        "",
        hint,
    ]
    return "\n".join(lines)


async def update_card(bot: Bot, state: FSMContext, text: str, kb) -> None:
    """Обновляет единственное сообщение-карточку.

    Если карточку удалили или редактировать нельзя — отправляет новую
    и запоминает её id.
    """
    data = await state.get_data()
    chat_id, card_id = data.get("chat_id"), data.get("card_id")
    if chat_id and card_id:
        try:
            await bot.edit_message_text(
                chat_id=chat_id, message_id=card_id, text=text, reply_markup=kb
            )
            return
        except TelegramBadRequest as e:
            if "message is not modified" in str(e):
                return
            # карточка удалена/недоступна — шлём новую
        except Exception:
            pass  # любая другая ошибка редактирования — тоже шлём новую
    target_chat = chat_id or data.get("chat_id")
    if not target_chat:
        return  # нет chat_id — ничего не делаем
    new_msg = await bot.send_message(target_chat, text, reply_markup=kb)
    await state.update_data(chat_id=new_msg.chat.id, card_id=new_msg.message_id)


# ---------- Команды ----------

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        f"👋 Добро пожаловать! Запись к мастеру {MASTER_NAME} ({MASTER_CONTACT}).\n\n"
        "Нажмите кнопку ниже и заполните анкету — всё будет в одном сообщении 👇",
        reply_markup=start_kb(),
    )


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Запись отменена. Чтобы начать заново — /start", reply_markup=NO_KB)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    lines = ["💰 Прайс:", ""]
    for name, price in PRICES.items():
        lines.append(f"• {name} — {price} ₽")
    await message.answer("\n".join(lines))


# ---------- Шаги записи ----------

@router.callback_query(F.data == "book")
async def step_service(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await state.clear()
    await state.set_state(BookingStates.choosing_service)
    await state.update_data(chat_id=callback.from_user.id, card_id=callback.message.message_id)
    text = render_card({}, "1️⃣ Выберите услугу:")
    await update_card(bot, state, text, services_kb())
    await callback.answer()


@router.callback_query(BookingStates.choosing_service, F.data.startswith("svc:"))
async def step_date(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    service, price = list(PRICES.items())[int(callback.data.split(":")[1])]
    await state.update_data(service=service, price=price)
    await state.set_state(BookingStates.choosing_date)
    data = await state.get_data()
    text = render_card(data, "2️⃣ Выберите дату (столбцы — Пн–Вс):")
    await update_card(bot, state, text, calendar_kb())
    await callback.answer()


@router.callback_query(BookingStates.choosing_date, F.data.startswith("date:"))
async def step_time(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    chosen_iso = callback.data.split(":", 1)[1]
    slots = db.get_available_slots(chosen_iso)
    if not slots:
        await callback.answer("На эту дату всё занято 😔 Выберите другую.", show_alert=True)
        return

    await state.update_data(date=chosen_iso)
    await state.set_state(BookingStates.choosing_time)
    data = await state.get_data()
    text = render_card(data, "3️⃣ Выберите время:")
    await update_card(bot, state, text, times_kb(chosen_iso))
    await callback.answer()


@router.callback_query(BookingStates.choosing_time, F.data.startswith("time:"))
async def step_name(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    slot = callback.data.split(":", 1)[1]  # время содержит ":", режем только первый
    data = await state.get_data()
    if slot not in db.get_available_slots(data["date"]):
        await state.clear()
        await callback.message.edit_text("😔 Это время только что заняли. Начните запись заново:")
        await callback.message.answer("Записаться:", reply_markup=start_kb())
        await callback.answer("Время уже занято", show_alert=True)
        return

    await state.update_data(time=slot)
    await state.set_state(BookingStates.waiting_name)
    text = render_card(await state.get_data(), "4️⃣ Напишите имя и фамилию (текстом):")
    await update_card(bot, state, text, only_cancel_kb())
    await callback.answer()


@router.callback_query(F.data == "off")
async def day_unavailable(callback: CallbackQuery) -> None:
    await callback.answer("Эта дата недоступна 🙏", show_alert=True)


@router.callback_query(F.data == "wd")
async def weekday_header(callback: CallbackQuery) -> None:
    """Нажатие на заголовок дня недели — ничего не делаем."""
    await callback.answer()


@router.callback_query(F.data == "cancel")
async def step_cancel(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    await state.clear()
    chat_id, card_id = data.get("chat_id"), data.get("card_id")
    if chat_id and card_id:
        try:
            await bot.edit_message_text(
                chat_id=chat_id, message_id=card_id,
                text="❌ Запись отменена. Начать заново — /start",
                reply_markup=None,
            )
        except TelegramBadRequest:
            pass
    await callback.answer()


@router.message(BookingStates.waiting_name, F.text == CANCEL_TEXT)
@router.message(BookingStates.waiting_phone, F.text == CANCEL_TEXT)
async def step_cancel_reply(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("❌ Запись отменена. Начать заново — /start", reply_markup=NO_KB)


@router.message(BookingStates.waiting_name, F.text)
async def step_phone(message: Message, state: FSMContext, bot: Bot) -> None:
    name = " ".join(message.text.split())
    if len(name) < 3 or " " not in name or not name.replace(" ", "").isalpha():
        await message.answer("Нужно имя и фамилия, например: Анна Иванова 🙂")
        return
    await state.update_data(name=name)
    await state.set_state(BookingStates.waiting_phone)
    text = render_card(
        await state.get_data(),
        "5️⃣ Напишите номер телефона в формате +7 999 123-45-67:",
    )
    await update_card(bot, state, text, only_cancel_kb())


@router.message(BookingStates.waiting_phone, F.contact)
async def step_phone_from_contact(message: Message, state: FSMContext, bot: Bot) -> None:
    await _show_confirm(message, state, bot, normalize_phone(message.contact.phone_number))


@router.message(BookingStates.waiting_phone, F.text)
async def step_phone_text(message: Message, state: FSMContext, bot: Bot) -> None:
    phone = message.text.strip()
    if not PHONE_RE.match(phone):
        await message.answer(
            "Кажется, номер набран неверно 🤔\nФормат: +7 999 123-45-67 или 89991234567"
        )
        return
    await _show_confirm(message, state, bot, normalize_phone(phone))


async def _show_confirm(message: Message, state: FSMContext, bot: Bot, phone: str) -> None:
    await state.update_data(phone=phone)
    await state.set_state(BookingStates.confirming)
    text = render_card(await state.get_data(), "✅ Всё верно? Нажмите «Подтвердить».")
    await update_card(bot, state, text, confirm_kb())


@router.callback_query(BookingStates.confirming, F.data == "confirm")
async def step_confirm(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    if data["time"] not in db.get_available_slots(data["date"]):
        await state.clear()
        await callback.message.edit_text("😔 Это время только что заняли. Начните запись заново:")
        await callback.message.answer("Записаться:", reply_markup=start_kb())
        await callback.answer("Время занято", show_alert=True)
        return

    db.add_booking(
        user_id=callback.from_user.id,
        user_name=data["name"],
        phone=data["phone"],
        service=data["service"],
        price=data["price"],
        date=data["date"],
        time=data["time"],
    )
    await state.clear()

    pretty = fmt_date(parse_date(data["date"]))
    final = (
        f"🎉 Вы записаны!\n\n"
        f"💅 {data['service']} — {data['price']} ₽\n"
        f"📅 {pretty}\n"
        f"🕐 {data['time']}\n"
        f"👤 {data['name']}\n"
        f"📞 {data['phone']}\n\n"
        f"Ждём вас! Вопросы — {MASTER_CONTACT}"
    )
    await callback.message.edit_text(final, reply_markup=None)
    await callback.message.answer("Хотите записаться ещё раз?", reply_markup=start_kb())

    admin_text = (
        f"🔔 Новая запись!\n\n"
        f"👤 {data['name']}\n📞 {data['phone']}\n"
        f"💅 {data['service']} ({data['price']} ₽)\n"
        f"📅 {pretty}\n🕐 {data['time']}"
    )
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, admin_text)
        except Exception:
            pass
    await callback.answer()


# ---------- Команды администратора ----------

@router.message(Command("bookings"))
async def cmd_bookings(message: Message) -> None:
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ У вас нет прав.")
        return
    rows = db.get_bookings(date.today().isoformat())
    if not rows:
        await message.answer("📭 На сегодня записей нет.")
        return
    lines = [f"📆 Записи на {fmt_date(date.today())}:", ""]
    for r in rows:
        lines.append(f"🕐 {r['time']} — {r['user_name']}, {r['phone']}\n     💅 {r['service']} ({r['price']} ₽)")
    await message.answer("\n".join(lines))


@router.message(Command("all"))
async def cmd_all(message: Message) -> None:
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ У вас нет прав.")
        return
    rows = db.get_bookings()
    if not rows:
        await message.answer("📭 Записей пока нет.")
        return
    lines, last_date = [], None
    for r in rows:
        if r["date"] != last_date:
            last_date = r["date"]
            lines += ["", f"📆 {fmt_date(parse_date(r['date']))}"]
        lines.append(f"🕐 {r['time']} — {r['user_name']}, {r['phone']} ({r['service']})")
    await message.answer("📒 Все записи:" + "\n".join(lines))


# ---------- Fallback: реагируем на любую необработанную кнопку ----------

@router.callback_query()
async def fallback_callback(callback: CallbackQuery, state: FSMContext) -> None:
    """Ловит нажатия кнопок из старых сессий (после перезапуска бота)."""
    await state.clear()
    await callback.message.answer(
        "⚠️ Эта кнопка устарела. Пожалуйста, начните запись заново: /start",
        reply_markup=start_kb(),
    )
    await callback.answer()


# ---------- Fallback: реагируем на любое входящее сообщение ----------

@router.message()
async def fallback_message(message: Message, state: FSMContext) -> None:
    """Бот никогда не молчит: отвечаем на любое необработанное сообщение."""
    st = await state.get_state()
    if st == BookingStates.waiting_name.state:
        await message.answer("Напишите, пожалуйста, имя и фамилию текстом 🙂")
    elif st == BookingStates.waiting_phone.state:
        await message.answer("Напишите номер телефона текстом, например +7 999 123-45-67")
    elif st:
        await message.answer("Выбирайте варианты кнопками в карточке выше 🙂")
    else:
        await message.answer(
            "Я бот записи на маникюр 💅\nЧтобы записаться — /start",
        )
