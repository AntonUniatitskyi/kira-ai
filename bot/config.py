import os
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

# --- OpenRouter ---
OPENROUTER_API_KEY = _require("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

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
