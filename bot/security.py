"""
Security Gateway.

Единственная задача: пропускать дальше по цепочке обработки только
сообщения от ALLOWED_USER_ID. Все остальные — молча дропаются,
без единого ответа (чтобы не спалить сам факт существования бота
и не тратить лимиты OpenRouter на чужие сообщения).
"""
import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update

from bot.config import ALLOWED_USER_ID

logger = logging.getLogger("kira.security")


class WhitelistMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")

        if user is None or user.id != ALLOWED_USER_ID:
            if user is not None:
                # Логируем сам факт попытки, но НЕ отвечаем этому пользователю
                logger.warning(
                    "Заблокирован чужой запрос: user_id=%s username=%s",
                    user.id,
                    user.username,
                )
            return  # молча игнорируем, дальше по цепочке не идём

        return await handler(event, data)
