import asyncio
import time
import psutil
from bot import db

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_system_status",
            "description": "Получить статус системы сервера: использование оперативной памяти (RAM), свободное место на диске и время непрерывной работы (uptime).",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_docker_status",
            "description": "Получить список запущенных Docker-контейнеров и их текущий статус.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save_memory",
            "description": "Сохранить важный факт о пользователе, сервере или окружении в долговременную память. Перезаписывает старое значение, если ключ уже существует.",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "Краткий ключ факта (например: 'кошка', 'порт_dev_сервера', 'имя_жены')"
                    },
                    "value": {
                        "type": "string",
                        "description": "Значение факта (например: 'Мурка', '8080')"
                    }
                },
                "required": ["key", "value"]
            }
        }
    }
]


async def get_system_status() -> str:
    mem = psutil.virtual_memory()
    ram_total = mem.total / (1024 ** 3)
    ram_used = (mem.total - mem.available) / (1024 ** 3)
    disk = psutil.disk_usage('/')
    disk_total = disk.total / (1024 ** 3)
    disk_free = disk.free / (1024 ** 3)
    uptime_seconds = time.time() - psutil.boot_time()
    uptime_days = int(uptime_seconds // 86400)
    uptime_hours = int((uptime_seconds % 86400) // 3600)
    uptime_minutes = int((uptime_seconds % 3600) // 60)

    uptime_str = f"{uptime_days} дн. {uptime_hours} ч. {uptime_minutes} мин." if uptime_days > 0 else f"{uptime_hours} ч. {uptime_minutes} мин."
    report = (
        f"Статус Ubuntu сервера:\n"
        f"- RAM: {ram_used:.1f}GB / {ram_total:.1f}GB (Занято: {mem.percent}%)\n"
        f"- Диск (/): Свободно {disk_free:.1f}GB из {disk_total:.1f}GB (Занято: {disk.percent}%)\n"
        f"- Uptime: {uptime_str}"
    )
    return report

async def get_docker_status() -> str:
    process = await asyncio.create_subprocess_exec(
        "docker", "ps",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        return f"Ошибка выполнения команды docker ps:\n{stderr.decode('utf-8')}"
    if stdout:
        return stdout.decode('utf-8')

    return "Нет запущенных контейнеров или пустой вывод."


def build_tools_registry(user_id: int) -> dict:
    async def save_memory(key: str, value: str) -> str:
        # Функция захватывает user_id из области видимости фабрики
        await db.save_fact(user_id, key, value)
        return f"✅ Запомнила: {key} = {value}"

    return {
        "get_system_status": get_system_status,
        "get_docker_status": get_docker_status,
        "save_memory": save_memory,
    }

TOOL_DESCRIPTIONS = {
    "get_system_status": "Гляну статы сервера...",
    "get_docker_status": "Смотрю докер...",
}