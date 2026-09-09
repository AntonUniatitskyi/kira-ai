import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message

from bot import db
from bot.config import ALLOWED_USER_ID, TG_TOKEN
from bot.llm import ask_kira
from bot.security import WhitelistMiddleware
from bot.tools import TOOL_DESCRIPTIONS

from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("kira.main")

bot = Bot(token=TG_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN))
dp = Dispatcher()

# Вешаем whitelist и на сообщения, и на любые другие апдейты (на будущее,
# если добавишь кнопки/callback'и)
dp.update.outer_middleware(WhitelistMiddleware())


@dp.message(Command("clear", "reset"))
async def cmd_clear(message: Message) -> None:
    deleted = await db.clear_history(message.from_user.id)
    await message.answer(f"Готово, стёрла историю ({deleted} сообщений). Начинаем с чистого листа.")


@dp.message(F.text)
async def handle_message(message: Message) -> None:
    async def keep_typing():
        try:
            while True:
                await bot.send_chat_action(chat_id=message.chat.id, action="typing")
                await asyncio.sleep(4)
        except asyncio.CancelledError:
            # Сюда мы попадем, когда кто-то снаружи вызовет task.cancel()
            pass

    user_id = message.from_user.id
    user_text = message.text

    async def notify_tool(func_name: str):
        text = TOOL_DESCRIPTIONS.get(
            func_name,
            f"⚙️ Выполняю команду на сервере ({func_name})..."
        )
        await message.answer(text)
        await bot.send_chat_action(chat_id=message.chat.id, action="typing")

    typing_task = asyncio.create_task(keep_typing())

    try:
        history = await db.get_history(user_id)
        facts = await db.get_all_facts(user_id)
        reply_text = await ask_kira(
            history=history,
            facts=facts,
            user_message=user_text,
            user_id=user_id,
            on_tool_call=notify_tool
        )
        await db.save_message(user_id, "user", user_text)
        await db.save_message(user_id, "assistant", reply_text)

        await message.answer(reply_text)
    except Exception as e:
        logger.exception("Ошибка при обработке сообщения")
        await message.answer(f"Блин, апишка отвалилась. Ошибка: {e}")
    finally:
        typing_task.cancel()


async def main() -> None:
    await db.init_pool()
    logger.info("Кира проснулась и слушает Telegram (owner_id=%s)...", ALLOWED_USER_ID)
    try:
        await dp.start_polling(bot)
    finally:
        await db.close_pool()


if __name__ == "__main__":
    asyncio.run(main())
