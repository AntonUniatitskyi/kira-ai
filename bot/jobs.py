import logging
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.config import TG_TOKEN

logger = logging.getLogger("kira.jobs")

async def send_reminder(user_id: int, text: str) -> None:
    bot = Bot(token=TG_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    try:
        await bot.send_message(chat_id=user_id, text=f"🔔 **Напоминание:**\n{text}")
        logger.info("Успешно отправлено напоминание юзеру %s", user_id)
    except Exception as e:
        logger.error("Ошибка при отправке напоминания: %s", e)
    finally:
        await bot.session.close()