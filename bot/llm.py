import json
import logging
from datetime import datetime
from typing import Awaitable, Callable, Optional

from openai import APIError, AsyncOpenAI

from bot.config import (
    LLM_TIMEOUT, MAX_TOOL_ITERATIONS, PROVIDER_CHAIN, SYSTEM_PROMPT, Provider,
)
from bot.tools import TOOL_SCHEMAS, build_tools_registry

logger = logging.getLogger("kira.llm")

# Заглушка из доков Google для tool_calls, у которых нет настоящей подписи Gemini
GEMINI_SKIP_SIGNATURE = "skip_thought_signature_validator"


class AllProvidersFailed(Exception):
    """Ни один провайдер из цепочки не ответил."""


# max_retries=0: SDK сам ретраит 429/5xx с паузами, а нам нужен мгновенный fallback.
# Записи цепочки с одним client_id (обе GLM) делят один клиент.
_clients: dict[str, AsyncOpenAI] = {}
for _p in PROVIDER_CHAIN:
    if _p.client_id not in _clients:
        _clients[_p.client_id] = AsyncOpenAI(
            base_url=_p.base_url,
            api_key=_p.api_key,
            max_retries=0,
            timeout=LLM_TIMEOUT,
        )


def _assistant_message(msg) -> dict:
    """Каноничное assistant-сообщение: только role/content/tool_calls.
    Поля вроде reasoning_content отбрасываются. extra_content (подпись Gemini)
    сохраняем, при отправке его подчистит _prepare_messages."""
    tool_calls = []
    for tc in msg.tool_calls:
        item = {
            "id": tc.id,
            "type": "function",
            "function": {"name": tc.function.name, "arguments": tc.function.arguments},
        }
        extra = (tc.model_extra or {}).get("extra_content")
        if extra:
            item["extra_content"] = extra
        tool_calls.append(item)
    return {"role": "assistant", "content": msg.content or "", "tool_calls": tool_calls}


def _prepare_messages(messages: list[dict], provider: Provider) -> list[dict]:
    """Подгоняет историю под конкретного провайдера."""
    out = []
    for m in messages:
        tool_calls = m.get("tool_calls")
        if m.get("role") != "assistant" or not tool_calls:
            out.append(m)
            continue

        new_calls = []
        for i, tc in enumerate(tool_calls):
            tc = dict(tc)
            extra = tc.pop("extra_content", None)
            if provider.is_gemini:
                sig = ((extra or {}).get("google") or {}).get("thought_signature")
                # Gemini 3 требует подпись у первого functionCall каждого хода
                if sig or i == 0:
                    tc["extra_content"] = {
                        "google": {"thought_signature": sig or GEMINI_SKIP_SIGNATURE}
                    }
            new_calls.append(tc)
        out.append({**m, "tool_calls": new_calls})
    return out


def _log_failure(provider: Provider, e: APIError) -> None:
    status = getattr(e, "status_code", None)
    if status in (401, 403):
        logger.error("КЛЮЧ %s ОТКЛОНЁН (HTTP %s), проверь .env: %s", provider.name, status, e)
    elif status in (400, 404, 422):
        logger.error("%s отклонил запрос (HTTP %s): %s", provider.name, status, e)
    else:
        logger.warning("%s не ответил (%s): %s", provider.name, type(e).__name__, e)


async def _chat(messages: list[dict], use_tools: bool):
    """Идёт по цепочке до первого успешного ответа."""
    last_error: Optional[Exception] = None
    for provider in PROVIDER_CHAIN:
        kwargs = {
            "model": provider.model,
            "messages": _prepare_messages(messages, provider),
        }
        if use_tools:
            kwargs["tools"] = TOOL_SCHEMAS
        if provider.extra_body:
            kwargs["extra_body"] = provider.extra_body

        try:
            response = await _clients[provider.client_id].chat.completions.create(**kwargs)
        except APIError as e:  # включает таймауты, сеть, 429, 4xx, 5xx
            last_error = e
            _log_failure(provider, e)
            continue

        if not response.choices:
            logger.warning("%s вернул пустой choices", provider.name)
            continue

        logger.info("Ответил провайдер %s", provider.name)
        return response

    raise AllProvidersFailed("Все LLM-провайдеры недоступны") from last_error


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
        response = await _chat(messages, use_tools)

        message_obj = response.choices[0].message
        tool_calls = message_obj.tool_calls
        if not tool_calls:
            break

        messages.append(_assistant_message(message_obj))
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
                "content": str(result),
            })
    else:
        return "Уф, слишком много действий на сервере подряд, я запуталась. Давай чуть проще?"

    reply = message_obj.content
    if not reply:
        logger.warning("LLM вернула пустой ответ, finish_reason=%s",
                       response.choices[0].finish_reason)
        reply = "Хм, я зависла и ничего не ответила. Спроси ещё раз?"

    return reply