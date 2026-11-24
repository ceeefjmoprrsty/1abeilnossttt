"""Модуль базы данных. Таблица bookings хранит все записи."""

import sqlite3
from typing import Optional

from config import DB_PATH


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    """Создаёт таблицу, если нет."""
    with _get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bookings (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                user_name   TEXT    NOT NULL,
                phone       TEXT    NOT NULL,
                service     TEXT    NOT NULL,
                price       INTEGER NOT NULL,
                date        TEXT    NOT NULL,
                time        TEXT    NOT NULL,
                created_at  TEXT    DEFAULT (datetime('now','localtime'))
            )
            """
        )
        conn.commit()


def get_bookings(date: Optional[str] = None) -> list[sqlite3.Row]:
    """Возвращает записи. Если указана дата — только за неё."""
    conn = _get_conn()
    if date:
        cursor = conn.execute(
            "SELECT * FROM bookings WHERE date = ? ORDER BY time", (date,)
        )
    else:
        cursor = conn.execute(
            "SELECT * FROM bookings ORDER BY date, time"
        )
    rows = cursor.fetchall()
    conn.close()
    return rows


def add_booking(
    user_id: int,
    user_name: str,
    phone: str,
    service: str,
    price: int,
    date: str,
    time: str,
) -> None:
    """Добавляет новую запись."""
    with _get_conn() as conn:
        conn.execute(
            """
            INSERT INTO bookings (user_id, user_name, phone, service, price, date, time)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, user_name, phone, service, price, date, time),
        )


def get_available_slots(date: str) -> list[str]:
    """Возвращает свободные временные слоты на дату."""
    from config import WORK_START_HOUR, WORK_END_HOUR, SLOT_HOURS

    conn = _get_conn()
    cursor = conn.execute(
        "SELECT time FROM bookings WHERE date = ? ORDER BY time", (date,)
    )
    taken = {row["time"] for row in cursor.fetchall()}
    conn.close()

    slots = []
    h = WORK_START_HOUR
    while h < WORK_END_HOUR:
        slot = f"{h:02d}:00"
        if slot not in taken:
            slots.append(slot)
        h += SLOT_HOURS
    return slots


def get_booked_counts(date_from: str, date_to: str) -> dict[str, int]:
    """Возвращает {iso_дата: число занятых слотов} для диапазона дат (для календаря)."""
    conn = _get_conn()
    cursor = conn.execute(
        """
        SELECT date, COUNT(*) AS cnt
        FROM bookings
        WHERE date BETWEEN ? AND ?
        GROUP BY date
        """,
        (date_from, date_to),
    )
    result = {row["date"]: row["cnt"] for row in cursor.fetchall()}
    conn.close()
    return result
