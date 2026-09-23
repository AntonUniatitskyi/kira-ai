import json

import logging
from typing import Callable, Awaitable, Optional
from openai import AsyncOpenAI
from bot.config import LLM_MODEL, OPENROUTER_API_KEY, OPENROUTER_BASE_URL, SYSTEM_PROMPT, MAX_TOOL_ITERATIONS
from bot.tools import TOOL_SCHEMAS, build_tools_registry
from datetime import datetime
logger = logging.getLogger("kira.llm")

client = AsyncOpenAI(
    base_url=OPENROUTER_BASE_URL,
    api_key=OPENROUTER_API_KEY,
)

async def ask_kira(
        history: list[dict],
        facts: dict,
        user_message: str,
        user_id: int,
        scheduler,
        use_tools: bool = True,
        on_tool_call: Optional[Callable[[str], Awaitable[None]]] = None
) -> str:
    registry = build_tools_registry(user_id, scheduler)
    final_system_prompt = SYSTEM_PROMPT

    if facts:
        facts_str = "\n".join(f"- {k}: {v}" for k, v in facts.items())
        final_system_prompt += f"\n\nТЕКУЩИЕ ФАКТЫ ИЗ ПАМЯТИ (ты сама их записала ранее):\n{facts_str}"

    weekdays_ru = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
    current_weekday = weekdays_ru[datetime.now().weekday()]
    now_str = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ({current_weekday})"
    final_system_prompt += f"\n\nТЕКУЩЕЕ ВРЕМЯ СИСТЕМЫ (Киев): {now_str}. Опирайся на него при установке напоминаний."

    messages = [{"role": "system", "content": final_system_prompt}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_message})

    for _ in range(MAX_TOOL_ITERATIONS):
        kwargs = {
            "model": LLM_MODEL,
            "messages": messages,
        }
        if use_tools:
            kwargs["tools"] = TOOL_SCHEMAS

        response = await client.chat.completions.create(**kwargs)

        message_obj = response.choices[0].message
        tool_calls = message_obj.tool_calls
        if not tool_calls:
            break

        messages.append(message_obj.model_dump(exclude_none=True))
        for tool_call in tool_calls:
            func_name = tool_call.function.name

            if on_tool_call is not None:
                await on_tool_call(func_name)
            try:
                func_args = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                func_args = {}

            func = registry.get(func_name)
            if func:
                try:
                    result = await func(**func_args)
                except Exception as e:
                    result = f"Внутренняя ошибка функции {func_name}: {e}"
            else:
                result = f"Ошибка: функция {func_name} не найдена в реестре сервера."

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "name": func_name,
                "content": str(result)
            })
    else:
        return "Уф, слишком много действий на сервере подряд, я запуталась. Давай чуть проще?"

    reply = message_obj.content
    if not reply:
        logger.warning("LLM вернула пустой ответ, finish_reason=%s",
                        response.choices[0].finish_reason)
        reply = "Хм, я зависла и ничего не ответила. Спроси ещё раз?"

    return reply
