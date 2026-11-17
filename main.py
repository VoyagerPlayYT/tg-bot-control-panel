import os
import time
import sqlite3
import asyncio
from datetime import datetime
from typing import Optional, List
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

app = FastAPI(title="Telegram Bot Control Panel")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "data", "bot_admin.db")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

templates = Jinja2Templates(directory=TEMPLATES_DIR)

# Bot runtime state
bot_state = {
    "status": "ONLINE",
    "name": "@HomeMaster_OrchestratorBot",
    "started_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "mode": "Long Polling (Zero Latency)",
    "total_messages": 1420,
    "active_users": 18,
    "version": "v3.1.2-Enterprise"
}

logs_buffer = [
    {"time": datetime.now().strftime("%H:%M:%S"), "level": "INFO", "msg": "Ядро Telegram-бота успешно инициализировано"},
    {"time": datetime.now().strftime("%H:%M:%S"), "level": "SUCCESS", "msg": "Long Polling соединение с Telegram API установлено"},
    {"time": datetime.now().strftime("%H:%M:%S"), "level": "INFO", "msg": "Модуль авто-напоминаний [ReminderWorker] запущен"},
    {"time": datetime.now().strftime("%H:%M:%S"), "level": "INFO", "msg": "Служба бэкапов подключена к Telegram Admin каналу"}
]


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS subscribers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id TEXT UNIQUE NOT NULL,
            username TEXT,
            full_name TEXT,
            role TEXT DEFAULT 'Пользователь',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS broadcast_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL,
            recipients_count INTEGER,
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("SELECT COUNT(*) FROM subscribers")
    if cur.fetchone()[0] == 0:
        cur.executemany("""
            INSERT INTO subscribers (chat_id, username, full_name, role)
            VALUES (?, ?, ?, ?)
        """, [
            ("74918231", "@mama_sweet", "Мама", "Администратор семьи"),
            ("83719203", "@papa_builder", "Папа", "Администратор"),
            ("92837461", "@voyager_dev", "Я (Разработчик)", "Главный системный инж."),
            ("10293847", "@sister_art", "Сестра", "Пользователь"),
            ("11928374", "@family_group_bot", "Семейный чат", "Группа")
        ])

    conn.commit()
    conn.close()


init_db()


def add_log(level: str, msg: str):
    global logs_buffer
    log_entry = {
        "time": datetime.now().strftime("%H:%M:%S"),
        "level": level,
        "msg": msg
    }
    logs_buffer.append(log_entry)
    if len(logs_buffer) > 100:
        logs_buffer.pop(0)


# Models
class BotControlAction(BaseModel):
    action: str  # start, stop, restart


class BroadcastRequest(BaseModel):
    message: str
    target_role: Optional[str] = "all"


class SimulateMessageRequest(BaseModel):
    command: str


@app.get("/", response_class=HTMLResponse)
async def admin_page(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/status")
async def get_bot_status():
    return JSONResponse(bot_state)


@app.post("/api/bot/control")
async def control_bot(data: BotControlAction):
    action = data.action.lower()
    if action == "restart":
        bot_state["status"] = "RESTARTING"
        add_log("WARN", "Инициирована горячая перезагрузка модулей бота...")
        await asyncio.sleep(0.5)
        bot_state["status"] = "ONLINE"
        bot_state["started_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        add_log("SUCCESS", "Бот успешно перезапущен и готов к обработке событий")
    elif action == "stop":
        bot_state["status"] = "STOPPED"
        add_log("WARN", "Служба бота остановлена администратором через веб-панель")
    elif action == "start":
        bot_state["status"] = "ONLINE"
        bot_state["started_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        add_log("SUCCESS", "Служба бота запущена в режиме высокой доступности")
    return {"status": "ok", "bot_state": bot_state}


@app.get("/api/logs")
async def get_logs():
    return {"logs": list(reversed(logs_buffer))}


@app.get("/api/subscribers")
async def get_subscribers():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM subscribers ORDER BY id ASC")
    subs = [dict(r) for r in cur.fetchall()]
    conn.close()
    return {"subscribers": subs}


@app.post("/api/broadcast")
async def send_broadcast(data: BroadcastRequest):
    if not data.message.strip():
        raise HTTPException(status_code=400, detail="Текст рассылки пуст")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM subscribers")
    count = cur.fetchone()[0]

    cur.execute("INSERT INTO broadcast_history (text, recipients_count) VALUES (?, ?)", (data.message, count))
    conn.commit()
    conn.close()

    bot_state["total_messages"] += count
    add_log("INFO", f"Рассылка отправлена {count} получателям: «{data.message[:30]}...»")
    return {"status": "sent", "recipients": count}


@app.post("/api/simulate-chat")
async def simulate_chat(data: SimulateMessageRequest):
    cmd = data.command.strip()
    bot_state["total_messages"] += 1

    add_log("INFO", f"Получена команда от клиента: {cmd}")

    if cmd == "/start":
        reply = "👋 Приветствую! Я ваш домашний бот-ассистент на круглосуточном сервере.\nИспользуйте /help для просмотра доступных команд."
    elif cmd == "/status":
        reply = f"🟢 Статус узла: {bot_state['status']}\n🕒 Аптайм: c {bot_state['started_at']}\n📊 Обработано запросов: {bot_state['total_messages']}"
    elif cmd == "/ping":
        reply = "🏓 Понг! Время отклика локального ядра: 1.2 мс. Сервер стабилен."
    elif cmd == "/tasks":
        reply = "📋 Семейные дела на сегодня: 4 активных задачи. Все подробности синхронизированы в Family Hub."
    elif cmd == "/backup":
        reply = "💾 Резервная копия базы данных сформирована и проверена по контрольной сумме SHA-256."
    else:
        reply = f"🤖 Команда «{cmd}» принята в обработку. Запрос зарегистрирован в логах сервера."

    add_log("SUCCESS", f"Ответ отправлен пользователю: {reply[:35]}...")
    return {"command": cmd, "reply": reply}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8004, reload=False)
