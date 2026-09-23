from datetime import datetime

import asyncio
import time
import psutil
from bot import db
from bot.jobs import send_reminder
import aiosqlite
import aiohttp
import json
import ipaddress
from bot.config import KNOWN_SUBNETS
import os

WMO_CODES = {
    0: "☀️ Ясно",
    1: "🌤 В основном ясно",
    2: "⛅ Частично облачно",
    3: "☁️ Пасмурно",
    45: "🌫 Туман",
    48: "🌫 Изморозь",
    51: "🌦 Лёгкая морось",
    53: "🌦 Морось",
    55: "🌦 Сильная морось",
    56: "🧊 Ледяная морось",
    57: "🧊 Сильная ледяная морось",
    61: "🌧 Небольшой дождь",
    63: "🌧 Дождь",
    65: "🌧 Ливень",
    66: "🧊 Ледяной дождь",
    67: "🧊 Сильный ледяной дождь",
    71: "🌨 Небольшой снег",
    73: "🌨 Снег",
    75: "🌨 Сильный снегопад",
    77: "❄️ Снежная крупа",
    80: "🌦 Кратковременный дождь",
    81: "🌧 Кратковременный ливень",
    82: "⛈ Сильный ливень",
    85: "🌨 Кратковременный снег",
    86: "🌨 Сильный кратковременный снег",
    95: "⛈ Гроза",
    96: "⛈ Гроза с градом",
    99: "⛈ Сильная гроза с градом",
}

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
    },
    {
        "type": "function",
        "function": {
            "name": "set_reminder",
            "description": "Установить напоминание. Планировщик отправит сообщение в указанное время.",
            "parameters": {
                "type": "object",
                "properties": {
                    "run_at": {
                        "type": "string",
                        "description": "Точное время срабатывания строго в формате 'YYYY-MM-DD HH:MM:SS'"
                    },
                    "text": {
                        "type": "string",
                        "description": "Текст напоминания, который нужно прислать"
                    }
                },
                "required": ["run_at", "text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_kpi_schedule",
            "description": "Получить расписание пар из КПИ. Возвращает расписание на 1 и 2 неделю с уже отфильтрованными (скрытыми) предметами пользователя. LLM должна сама определить, какая сейчас неделя и день.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "restart_docker_container",
            "description": "Перезапустить указанный Docker-контейнер.",
            "parameters": {
                "type": "object",
                "properties": {
                    "container_name": {
                        "type": "string",
                        "description": "Точное имя контейнера (например: 'kpi-schedule-bot' или 'nginx')"
                    }
                },
                "required": ["container_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_docker_logs",
            "description": "Получить последние строки логов указанного Docker-контейнера.",
            "parameters": {
                "type": "object",
                "properties": {
                    "container_name": {
                        "type": "string",
                        "description": "Точное имя контейнера"
                    },
                    "lines": {
                        "type": "integer",
                        "description": "Количество последних строк лога (по умолчанию 50)"
                    }
                },
                "required": ["container_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "scan_host_ports",
            "description": "Просканировать локальный IP-адрес на открытые порты. Принимает ТОЛЬКО валидные IPv4 адреса.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target_ip": {
                        "type": "string",
                        "description": "IPv4 адрес цели, например '192.168.1.100'"
                    }
                },
                "required": ["target_ip"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "scan_local_devices",
            "description": "Просканировать известную локальную подсеть на наличие подключенных устройств (поиск соседей по Wi-Fi).",
            "parameters": {
                "type": "object",
                "properties": {
                    "network": {
                        "type": "string",
                        "enum": ["main", "secondary"],
                        "description": "Какую сеть сканировать: 'main' (домашняя) или 'secondary' (гостевая/дополнительная)."
                    }
                },
                "required": ["network"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Получить текущую погоду в указанном городе. Если город не указан, берет локацию сервера.",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "Город на английском или русском (например: Kyiv, Бородянка)."
                    }
                }
            }
        }
    },
]

HTTP_HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}

def get_week_type(date: datetime) -> str:
    return "scheduleFirstWeek" if date.isocalendar()[1] % 2 == 0 else "scheduleSecondWeek"

def is_private_ip(ip: str) -> bool:
    ip_obj = ipaddress.ip_address(ip)
    return ip_obj.is_private or ip_obj.is_loopback

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

PROTECTED_CONTAINERS = {"kira-bot-db-1", "kira-bot-bot-1"}


async def restart_docker_container(container_name: str) -> str:
    if container_name in PROTECTED_CONTAINERS:
        return (
            f"❌ Отказ: Контейнер '{container_name}' находится в чёрном списке "
            f"(защищен от перезапуска). Я не могу перезапустить саму себя или системную БД."
        )

    process = await asyncio.create_subprocess_exec(
        "docker", "restart", container_name,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    _, stderr = await process.communicate()

    if process.returncode != 0:
        return f"❌ Ошибка рестарта {container_name}:\n{stderr.decode('utf-8')}"

    return f"✅ Контейнер {container_name} успешно перезапущен."


async def get_docker_logs(container_name: str, lines: int = 50) -> str:
    process = await asyncio.create_subprocess_exec(
        "docker", "logs", "--tail", str(lines), container_name,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await process.communicate()

    logs = stdout.decode('utf-8') + "\n" + stderr.decode('utf-8')
    logs = logs.strip()

    if not logs:
        return f"Логи контейнера {container_name} пусты."

    if len(logs) > 3000:
        logs = "...[УРЕЗАНО]...\n" + logs[-3000:]

    return f"Логи контейнера {container_name} (последние {lines} строк):\n{logs}"


async def scan_host_ports(target_ip: str) -> str:
    try:
        if not is_private_ip(target_ip):
            return (
                f"❌ Отказ: IP {target_ip} — публичный. "
                "Я могу сканировать только локальные сети."
            )
    except ValueError:
        return (
            f"❌ Ошибка: '{target_ip}' не является валидным IP-адресом. "
            "Нужен точный IPv4, например 192.168.1.1."
        )

    process = await asyncio.create_subprocess_exec(
        "nmap", "-F", "--open", "-Pn", target_ip,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        return f"❌ Ошибка nmap:\n{stderr.decode('utf-8')}"
    result = stdout.decode('utf-8').strip()

    return f"Результат сканирования {target_ip}:\n{result}"


async def scan_local_devices(network: str) -> str:
    subnet = KNOWN_SUBNETS.get(network)
    if not subnet:
        return (
            f"❌ Ошибка: неизвестный идентификатор сети '{network}'. "
            f"Доступные варианты: {', '.join(KNOWN_SUBNETS.keys())}."
        )

    process = await asyncio.create_subprocess_exec(
        "nmap", "-sn", subnet,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        return f"❌ Ошибка при сканировании подсети {network} ({subnet}):\n{stderr.decode('utf-8')}"

    result = stdout.decode('utf-8').strip()
    return f"Устройства в сети {network} ({subnet}):\n{result}"


async def get_weather(city: str = None) -> str:
    if not city:
        city = os.getenv("WEATHER_LOCATION")

    async with aiohttp.ClientSession() as session:
        try:
            if city:
                geo_url = "https://geocoding-api.open-meteo.com/v1/search"
                geo_params = {
                    "name": city,
                    "count": 1,
                    "language": "ru",
                    "format": "json"
                }
                async with session.get(geo_url, params=geo_params, timeout=5) as geo_resp:
                    geo_data = await geo_resp.json()
                    if not geo_data.get("results"):
                        return f"❌ Город '{city}' не найден."

                    location = geo_data["results"][0]
                    lat, lon = location["latitude"], location["longitude"]
                    target_name = location["name"]

            else:
                ip_url = "http://ip-api.com/json/"
                async with session.get(ip_url, timeout=5) as ip_resp:
                    ip_data = await ip_resp.json()
                    if ip_data.get("status") != "success":
                        return "❌ Не удалось определить местоположение сервера."

                    lat, lon = ip_data["lat"], ip_data["lon"]
                    target_name = ip_data["city"]

            weather_url = "https://api.open-meteo.com/v1/forecast"
            weather_params = {
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,apparent_temperature,wind_speed_10m,weather_code",
                "timezone": "auto"
            }

            async with session.get(weather_url, params=weather_params, timeout=5) as weather_resp:
                if weather_resp.status != 200:
                    return f"❌ Ошибка погодного сервиса (статус {weather_resp.status})."

                w_data = await weather_resp.json()
                current = w_data.get("current", {})
                temp = current.get("temperature_2m", "?")
                feels_like = current.get("apparent_temperature", "?")
                wind = current.get("wind_speed_10m", "?")
                w_code = current.get("weather_code", 0)

                condition = WMO_CODES.get(w_code, "❓ Неизвестно")

                return (
                    f"Погода в {target_name}:\n"
                    f"{condition}\n"
                    f"🌡 Температура: {temp}°C (Ощущается как {feels_like}°C)\n"
                    f"💨 Ветер: {wind} км/ч"
                )

        except Exception as e:
            return f"❌ Ошибка при получении погоды: {e}"

def build_tools_registry(user_id: int, scheduler=None) -> dict:
    async def save_memory(key: str, value: str) -> str:
        # Функция захватывает user_id из области видимости фабрики
        await db.save_fact(user_id, key, value)
        return f"✅ Запомнила: {key} = {value}"

    async def set_reminder(run_at: str, text: str) -> str:
        if not scheduler:
            return "❌ Ошибка: Планировщик не подключены."

        try:
            run_date = datetime.strptime(run_at, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return "❌ Ошибка формата времени. Используй 'YYYY-MM-DD HH:MM:SS'."

        scheduler.add_job(
            send_reminder,
            'date',
            run_date=run_date,
            args=[user_id, text]
        )
        return f"✅ Напоминание успешно установлено на {run_at}."

    async def get_kpi_schedule() -> str:
        old_bot_db_path = "/app/kpi_data/bot_data.db"

        try:
            async with aiosqlite.connect(old_bot_db_path) as db:
                cursor = await db.execute(
                    "SELECT group_id, group_name FROM user_groups WHERE user_key = ?",
                    (str(user_id),)
                )
                row = await cursor.fetchone()
                if not row:
                    return "❌ Я не знаю твою группу. Похоже, ты не зарегистрирован в старом боте."
                group_id, group_name = row[0], row[1]

                cursor = await db.execute(
                    "SELECT subject_name FROM user_hidden_subjects WHERE user_key = ? AND group_id = ?",
                    (str(user_id), group_id)
                )
                hidden_subjects = {r[0] for r in await cursor.fetchall()}

                cursor = await db.execute(
                    "SELECT subject_name, pair_type, url FROM subject_links WHERE group_id = ?",
                    (group_id,)
                )
                user_links = {(r[0], r[1]): r[2] for r in await cursor.fetchall()}

            schedule_url = f"https://api.campus.kpi.ua/schedule/lessons?groupId={group_id}"

            async with aiohttp.ClientSession() as session:
                async with session.get(schedule_url, headers=HTTP_HEADERS, timeout=5) as resp:
                    if resp.status != 200:
                        return f"❌ Ошибка API КПИ (статус {resp.status})"
                    schedule_data = await resp.json()

            current_week = 1 if get_week_type(datetime.now()) == "scheduleFirstWeek" else 2

            if isinstance(schedule_data, dict) and "data" in schedule_data:
                schedule_data = schedule_data["data"]

            if isinstance(schedule_data, dict):
                for week_key in ["scheduleFirstWeek", "scheduleSecondWeek"]:
                    for day in schedule_data.get(week_key, []):
                        filtered_pairs = []
                        for pair in day.get("pairs", []):
                            subj_name = pair.get("name")
                            pair_type = pair.get("type", "")

                            if subj_name in hidden_subjects:
                                continue

                            link = user_links.get((subj_name, pair_type))
                            if link:
                                pair["custom_connection_url"] = link

                            filtered_pairs.append(pair)
                        day["pairs"] = filtered_pairs
            ua_weekdays = ["Понеділок", "Вівторок", "Середа", "Четвер", "П'ятниця", "Субота", "Неділя"]
            today_ua = ua_weekdays[datetime.now().weekday()]
            return (
                f"Группа: {group_name}\n"
                f"ВАЖНО: Сейчас {current_week}-я учебная неделя по календарю КПИ. Сегодня {today_ua}.\n"
                f"Расписание (JSON):\n{json.dumps(schedule_data, ensure_ascii=False)}"
            )

        except Exception as e:
            return f"❌ Ошибка при получении расписания: {e}"

    return {
        "get_system_status": get_system_status,
        "get_docker_status": get_docker_status,
        "save_memory": save_memory,
        "set_reminder": set_reminder,
        "get_kpi_schedule": get_kpi_schedule,
        "restart_docker_container": restart_docker_container,  # <---
        "get_docker_logs": get_docker_logs,
        "scan_host_ports": scan_host_ports,
        "scan_local_devices": scan_local_devices,
        "get_weather": get_weather,
    }

TOOL_DESCRIPTIONS = {
    "get_system_status": "Гляну статы сервера...",
    "get_docker_status": "Смотрю докер...",
    "set_reminder": "Ставлю напоминалочку...",
    "get_kpi_schedule": "Иду на сайт смотреть тебе расписание...",
    "restart_docker_container": "Дергаю рубильник контейнера...",
    "get_docker_logs": "Читаю логи...",
    "scan_host_ports": "Сканирую открытые порты...",
    "scan_local_devices": "Сканирую Wi-Fi на наличие устройств...",
    "get_weather": "Смотрю погоду на улице...",
}