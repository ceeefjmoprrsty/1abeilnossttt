"""Постоянное FSM-хранилище на SQLite (переживает перезапуск бота)."""

import asyncio
import json
import sqlite3
from contextlib import asynccontextmanager, closing, contextmanager
from typing import Any, Iterator, Mapping

from aiogram.fsm.state import State
from aiogram.fsm.storage.base import (
    BaseEventIsolation,
    BaseStorage,
    StateType,
    StorageKey,
)

DB_PATH = "fsm_storage.db"

_lock = asyncio.Lock()


def _key_to_str(key: StorageKey) -> str:
    parts = [str(key.bot_id), str(key.chat_id), str(key.user_id), key.destiny or ""]
    return "|".join(p for p in parts if p)


class SQLiteStorage(BaseStorage):
    """Хранит state и data в SQLite — не теряется при перезапуске бота."""

    def __init__(self, path: str = DB_PATH) -> None:
        self.path = path
        with self._conn() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS fsm ("
                "k TEXT PRIMARY KEY, state TEXT, data TEXT)"
            )
            conn.commit()

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        """Открывает соединение и гарантирует его закрытие."""
        conn = closing(sqlite3.connect(self.path))
        with conn as c:
            yield c

    async def set_state(self, key: StorageKey, state: StateType = None) -> None:
        # aiogram передаёт объект State — сохраняем его строку "Group:name"
        value = state.state if isinstance(state, State) else state
        async with _lock:
            k = _key_to_str(key)
            with self._conn() as conn:
                if value is None:
                    conn.execute("UPDATE fsm SET state = NULL WHERE k = ?", (k,))
                else:
                    conn.execute(
                        "INSERT INTO fsm (k, state) VALUES (?, ?) "
                        "ON CONFLICT(k) DO UPDATE SET state = excluded.state",
                        (k, value),
                    )
                conn.commit()

    async def get_state(self, key: StorageKey) -> str | None:
        async with _lock:
            k = _key_to_str(key)
            with self._conn() as conn:
                row = conn.execute(
                    "SELECT state FROM fsm WHERE k = ?", (k,)
                ).fetchone()
                return row[0] if row else None

    async def set_data(self, key: StorageKey, data: Mapping[str, Any]) -> None:
        async with _lock:
            k = _key_to_str(key)
            with self._conn() as conn:
                conn.execute(
                    "INSERT INTO fsm (k, data) VALUES (?, ?) "
                    "ON CONFLICT(k) DO UPDATE SET data = excluded.data",
                    (k, json.dumps(dict(data), ensure_ascii=False)),
                )
                conn.commit()

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        async with _lock:
            k = _key_to_str(key)
            with self._conn() as conn:
                row = conn.execute(
                    "SELECT data FROM fsm WHERE k = ?", (k,)
                ).fetchone()
                return json.loads(row[0]) if row and row[0] else {}

    async def close(self) -> None:
        pass


class SimpleIsolation(BaseEventIsolation):
    """Простейшая изоляция: не даёт двум апдейтам одного юзера обработаться параллельно."""

    @asynccontextmanager
    async def lock(self, key: StorageKey):
        yield

    async def close(self) -> None:
        pass
