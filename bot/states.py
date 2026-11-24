"""Определяет состояния FSM (машина состояний диалога)."""

from aiogram.fsm.state import State, StatesGroup


class BookingStates(StatesGroup):
    """Цепочка шагов при записи клиента."""

    choosing_service = State()   # выбор услуги из прайса
    choosing_date    = State()   # выбор даты
    choosing_time    = State()   # выбор времени
    waiting_name     = State()   # ожидает ФИО
    waiting_phone    = State()   # ожидает номер телефона
    confirming       = State()   # финальное подтверждение
