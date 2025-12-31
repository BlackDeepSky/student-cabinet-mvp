"""
FastAPI backend для личного кабинета студента.
Работает с SQLite и файловой системой.
"""

from fastapi import FastAPI, File, UploadFile, HTTPException, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import sqlite3
import os
import shutil
from pathlib import Path
from datetime import datetime

# Конфигурация
DB_PATH = "instance/app.db"
UPLOAD_BASE_DIR = "storage/submissions"

# Убедимся, что папка для загрузок существует
Path(UPLOAD_BASE_DIR).mkdir(parents=True, exist_ok=True)

app = FastAPI()

# Отдаём статические файлы (HTML, CSS, JS)
app.mount("/static", StaticFiles(directory="static"), name="static")

def get_db():
    """Возвращает подключение к БД с включёнными внешними ключами"""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")  # КРИТИЧЕСКИ ВАЖНО!
    conn.row_factory = sqlite3.Row  # Позволяет обращаться по имени колонки
    return conn

@app.get("/", response_class=HTMLResponse)
async def index():
    with open("static/index.html", encoding="utf-8") as f:
        return f.read()

@app.post("/api/login")
async def login(student_id: str = Form(...)):
    """
    Простая "авторизация" по student_id.
    Возвращает информацию о студенте или 404.
    """
    with get_db() as conn:
        cur = conn.execute(
            "SELECT id, last_name, first_name, patronymic, group_name FROM students WHERE student_id = ?",
            (student_id.strip(),)
        )
        student = cur.fetchone()
        if not student:
            raise HTTPException(404, "Студент не найден")
        return dict(student)

@app.get("/api/assignments/{student_id}")
async def get_assignments(student_id: str):
    """
    Возвращает список заданий для студента.
    Для каждого задания указывает, отправлено ли оно.
    """
    with get_db() as conn:
        # Получаем ID студента
        cur = conn.execute("SELECT id FROM students WHERE student_id = ?", (student_id,))
        student_row = cur.fetchone()
        if not student_row:
            raise HTTPException(404, "Студент не найден")
        student_id_int = student_row[0]

        # Получаем задания + информацию о сдаче
        cur = conn.execute("""
                SELECT
                    a.id,
                    a.title,
                    a.description,
                    a.deadline,
                    s.name AS subject,      -- ← имя предмета (полезнее для фронтенда)
                    sub.id IS NOT NULL as submitted,
                    sub.file_path
                FROM assignments a
                JOIN subjects s ON a.subject_id = s.id
                LEFT JOIN submissions sub
                    ON sub.assignment_id = a.id AND sub.student_id = ?
                ORDER BY a.deadline
            """, (student_id_int,))

        assignments = []
        for row in cur.fetchall():
            assignments.append({
                "id": row["id"],
                "subject": row["subject"],          # ← теперь это строка, например "Математика"
                "title": row["title"],
                "description": row["description"],
                "deadline": row["deadline"],
                "submitted": bool(row["submitted"]),
                "file_path": row["file_path"]
            })
        return assignments

@app.get("/api/grades/{student_id}")
async def get_grades(student_id: str):
    """Возвращает успеваемость студента"""
    with get_db() as conn:
        cur = conn.execute("""
            SELECT
                sub.name as subject,
                g.grade,
                g.status
            FROM grades g
            JOIN subjects sub ON g.subject_id = sub.id
            JOIN students s ON g.student_id = s.id
            WHERE s.student_id = ?
        """, (student_id,))
        return [dict(row) for row in cur.fetchall()]

@app.post("/api/submit/{assignment_id}")
async def submit_work(
    assignment_id: int,
    student_id: str = Form(...),
    file: UploadFile = File(...)
):
    """Принимает файл работы от студента"""
    if not file.filename:
        raise HTTPException(400, "Файл не выбран")

    with get_db() as conn:
        # 1. Найдём ID студента
        cur = conn.execute("SELECT id FROM students WHERE student_id = ?", (student_id,))
        student_row = cur.fetchone()
        if not student_row:
            raise HTTPException(404, "Студент не найден")
        student_id_int = student_row[0]

        # 2. Проверим, существует ли задание
        cur = conn.execute("SELECT id FROM assignments WHERE id = ?", (assignment_id,))
        if not cur.fetchone():
            raise HTTPException(404, "Задание не найдено")

        # 3. Убедимся, что студент ещё не отправлял эту работу
        cur = conn.execute("""
            SELECT 1 FROM submissions
            WHERE student_id = ? AND assignment_id = ?
        """, (student_id_int, assignment_id))
        if cur.fetchone():
            raise HTTPException(409, "Работа уже отправлена")

        # 4. Сохраним файл
        safe_filename = "".join(c if c.isalnum() or c in "._-" else "_" for c in file.filename)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{safe_filename}"
        
        # Путь: storage/submissions/{student_id}/{assignment_id}/...
        student_dir = os.path.join(UPLOAD_BASE_DIR, str(student_id_int), str(assignment_id))
        Path(student_dir).mkdir(parents=True, exist_ok=True)
        file_path = os.path.join(student_dir, filename)

        # Запишем файл
        with open(file_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        # 5. Запишем в БД
        conn.execute("""
            INSERT INTO submissions (student_id, assignment_id, file_path)
            VALUES (?, ?, ?)
        """, (student_id_int, assignment_id, file_path))

        return {"message": "Работа успешно отправлена!", "file": filename}