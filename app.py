"""
Личный кабинет заочного студента — MVP
Backend на FastAPI + PostgreSQL + Cloudflare R2

Точка сборки приложения: создаёт FastAPI, подключает middleware,
статику и роутеры. Вся логика вынесена в модули и пакет routers/.
"""

import os
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from db import get_db
from routers import (
    pages, auth_routes, student, teacher, admin,
    messages, announcements, files,
)


# === Безопасная инициализация БД ===
def init_database_if_needed():
    """Создаёт схему и заполняет тестовыми данными, если БД пустая."""
    try:
        from db_seed import init_db, seed_data
        init_db()
        with get_db() as conn:
            cur = conn.execute("SELECT COUNT(*) FROM students")
            count = cur.fetchone()[0]
        if count == 0:
            print("🔵 БД пуста. Заполняю тестовыми данными...")
            seed_data()
            print("✅ БД успешно создана.")
        else:
            print("✅ БД уже инициализирована.")
    except Exception as e:
        print(f"❌ Ошибка при инициализации БД: {e}")


init_database_if_needed()

# === Приложение ===
app = FastAPI()

# Настройка CORS
_cors_origins_env = os.environ.get("ALLOWED_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000")
_cors_origins = [o.strip() for o in _cors_origins_env.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

# Подключение статики
app.mount("/static", StaticFiles(directory="static"), name="static")

# Роутеры
app.include_router(pages.router)
app.include_router(auth_routes.router)
app.include_router(student.router)
app.include_router(teacher.router)
app.include_router(admin.router)
app.include_router(messages.router)
app.include_router(announcements.router)
app.include_router(files.router)
