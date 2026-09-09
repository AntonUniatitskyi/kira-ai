"""
Memory Engine. Хранит скользящее окно истории диалога в Postgres.
"""
import logging
from pathlib import Path
from typing import Optional

import asyncpg

from bot.config import DATABASE_URL, HISTORY_WINDOW

logger = logging.getLogger("kira.db")

_pool: Optional[asyncpg.Pool] = None


async def init_pool() -> None:
    global _pool
    _pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)

    schema_path = Path(__file__).parent.parent / "sql" / "init.sql"
    schema_sql = schema_path.read_text(encoding="utf-8")

    async with _pool.acquire() as conn:
        await conn.execute(schema_sql)

    logger.info("Пул к Postgres создан, схема применена")


async def close_pool() -> None:
    if _pool is not None:
        await _pool.close()


def _get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Пул БД не инициализирован — вызови init_pool() при старте")
    return _pool


async def save_message(user_id: int, role: str, content: str) -> None:
    query = "INSERT INTO messages (user_id, role, content) VALUES ($1, $2, $3)"
    async with _get_pool().acquire() as conn:
        await conn.execute(query, user_id, role, content)


async def get_history(user_id: int, limit: int = HISTORY_WINDOW) -> list[dict]:
    """
    Возвращает последние `limit` реплик пользователя в ХРОНОЛОГИЧЕСКОМ
    порядке (старые -> новые), готовые к подстановке в messages[] для LLM.
    """
    query = """
        SELECT role, content
        FROM messages
        WHERE user_id = $1
        ORDER BY created_at DESC
        LIMIT $2
    """
    async with _get_pool().acquire() as conn:
        rows = await conn.fetch(query, user_id, limit)

    # rows пришли в порядке "от новых к старым" — разворачиваем
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


async def clear_history(user_id: int) -> int:
    """Стирает всю историю пользователя. Возвращает число удалённых строк."""
    query = "DELETE FROM messages WHERE user_id = $1"
    async with _get_pool().acquire() as conn:
        result = await conn.execute(query, user_id)
    # asyncpg возвращает строку вида "DELETE 42"
    return int(result.split()[-1])

async def save_fact(user_id: int, key: str, value: str) -> None:
    """Сохраняет или перезаписывает факт о пользователе."""
    query = """
        INSERT INTO user_facts (user_id, key, value) 
        VALUES ($1, $2, $3)
        ON CONFLICT (user_id, key) 
        DO UPDATE SET 
            value = EXCLUDED.value,
            updated_at = CURRENT_TIMESTAMP;
    """
    async with _get_pool().acquire() as conn:
        await conn.execute(query, user_id, key, value)


async def get_all_facts(user_id: int) -> dict:
    """Возвращает все сохраненные факты пользователя в виде словаря."""
    query = "SELECT key, value FROM user_facts WHERE user_id = $1"

    async with _get_pool().acquire() as conn:
        rows = await conn.fetch(query, user_id)

    # Генератор словаря элегантно превращает список asyncpg.Record в обычный dict
    return {row["key"]: row["value"] for row in rows}
