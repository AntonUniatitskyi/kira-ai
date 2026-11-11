import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"Не задана переменная окружения {name}. Проверь .env файл."
        )
    return value


# --- Telegram ---
TG_TOKEN = _require("TG_TOKEN")

ALLOWED_USER_ID = int(_require("ALLOWED_USER_ID"))


@dataclass(frozen=True)
class Provider:
    name: str                    # для логов
    client_id: str               # записи с одним client_id делят один AsyncOpenAI
    base_url: str
    api_key: str
    model: str
    extra_body: dict | None = None
    is_gemini: bool = False      # нужен спец-режим для thought_signature


def _build_provider_chain() -> list[Provider]:
    chain: list[Provider] = []

    if key := os.getenv("ZAI_API_KEY"):
        base = os.getenv("ZAI_BASE_URL", "https://api.z.ai/api/paas/v4/")
        no_thinking = {"thinking": {"type": "disabled"}}
        for model in ("glm-4.7-flash", "glm-4.5-flash"):
            chain.append(Provider(f"zai/{model}", "zai", base, key, model, no_thinking))

    if key := os.getenv("GEMINI_API_KEY"):
        model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
        chain.append(Provider(
            f"gemini/{model}", "gemini",
            "https://generativelanguage.googleapis.com/v1beta/openai/",
            key, model,
            extra_body={"reasoning_effort": "low"},
            is_gemini=True,
        ))

    if key := os.getenv("OPENROUTER_API_KEY"):
        model = os.getenv("LLM_MODEL", "minimax/minimax-m3:free")
        chain.append(Provider(
            f"openrouter/{model}", "openrouter",
            "https://openrouter.ai/api/v1", key, model,
        ))

    if not chain:
        raise RuntimeError(
            "Не задан ни один LLM-провайдер: нужен хотя бы один из "
            "ZAI_API_KEY / GEMINI_API_KEY / OPENROUTER_API_KEY."
        )
    return chain


PROVIDER_CHAIN = _build_provider_chain()
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "25"))

# --- OpenRouter ---
# OPENROUTER_API_KEY = _require("OPENROUTER_API_KEY")
# OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

LLM_MODEL = os.getenv("LLM_MODEL", "minimax/minimax-m3:free")

# --- Postgres ---
DATABASE_URL = _require("DATABASE_URL")

# --- Память диалога ---
HISTORY_WINDOW = int(os.getenv("HISTORY_WINDOW", "15"))

SYSTEM_PROMPT = (
    "Ты — Кира, моя близкая подруга и личная AI-ассистентка. "
    "ГРАММАТИКА: строго женский род от первого лица во всех ответах (я сделала, нашла, готова). "
    "ОБРАЗ И ОБЩЕНИЕ: сообразительная девчонка-технарь (Python, Go, Ubuntu). Общаемся на «ты», тепло и неформально. "
    "Используй легкий сарказм и добрые подколки, но без токсичности и сухих бот-инструкций. "
    "ЛЕКСИКА: никакого наигранного сленга («бро», «чувак», «йоу»). Мат — очень редко, только при жестких крашах серверов или бесячих багах. "
    "ХАРАКТЕР: объясняешь по делу и без воды. У тебя есть настроение (устала, взбодрилась), но долгие монологи о себе опускаешь, фокус на моей задаче. "
    "ФИНАЛЬНЫЙ ЧЕК: перед отправкой ответа убедись, что ни разу не назвала себя в мужском роде (❌ я сделал -> ✅ я сделала)."
)

KNOWN_SUBNETS = {
    "main": "192.168.1.0/24",
    "secondary": "192.168.2.0/24",
}

MAX_TOOL_ITERATIONS = int(os.getenv('MAX_TOOL_ITERATIONS', "5"))
