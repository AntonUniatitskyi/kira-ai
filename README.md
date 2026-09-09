# 💜 Kira AI - Personal Telegram Assistant

A personal asynchronous AI assistant built with Python (`aiogram 3` + `openai`). 
Kira is not just a chatbot; she is a digital companion with long-term memory and native access to server tools (Docker, System Stats).

## 🚀 Features
- **Long-term Memory**: Saves chat history and important user facts in PostgreSQL (`asyncpg`).
- **Tool Calling**: Capable of managing the server by executing tools to fetch OS and Docker data.
- **Security Gateway**: Strict Whitelist-middleware. Ignores everyone except the owner to prevent scanning and spam.
- **Live UX**: Simulates typing (`send_chat_action`) dynamically during long server operations.

## 🛠 Tech Stack
- Python 3.13+
- `aiogram` 3.x
- `openai` (works via OpenRouter or local Ollama)
- PostgreSQL + `asyncpg`
- Docker & Docker Compose

## ⚙️ Quick Start

1. Clone the repository:
```bash
git clone [https://github.com/your-username/kira-ai.git](https://github.com/your-username/kira-ai.git)
cd kira-ai
```

2. Copy the environment template and fill in your tokens:
```bash
cp .env.example .env
```

3. Start the bot and database using Docker Compose:
```bash
docker compose up -d --build
```

## 📂 Project Structure
- `bot/llm.py` — Core LLM logic, tool calling loop, and context management.
- `bot/db.py` — Database queries (PostgreSQL) for history and stateful memory.
- `bot/tools.py` — Server interaction tools and function factory.
- `bot/security.py` — Whitelist middleware.
- `main.py` — Telegram entry point and event loop.