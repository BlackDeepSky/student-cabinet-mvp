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
from fastapi.responses import FileResponse
from typing import Optional

# Автоматическая инициализация БД при запуске
if not os.path.exists("instance/app.db"):
    print("База данных не найдена. Инициализирую...")
    import subprocess
    subprocess.run(["python", "seed_data.py"])
else:
    print("База данных найдена. Продолжаю.")

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
    Возвращает список заданий для студента, включая преподавателей по предметам.
    """
    with get_db() as conn:
        # Получаем ID студента
        cur = conn.execute("SELECT id FROM students WHERE student_id = ?", (student_id,))
        student_row = cur.fetchone()
        if not student_row:
            raise HTTPException(404, "Студент не найден")
        student_id_int = student_row[0]

        # Получаем задания + предмет + преподаватели
        cur = conn.execute("""
            SELECT
                a.id,
                a.title,
                a.description,
                a.deadline,
                s.name AS subject,
                GROUP_CONCAT(
                    t.last_name || ' ' || substr(t.first_name, 1, 1) || '.'
                    || CASE WHEN t.patronymic IS NOT NULL 
                        THEN substr(t.patronymic, 1, 1) || '.' 
                        ELSE '' END,
                    ', '
                ) AS teachers
            FROM assignments a
            JOIN subjects s ON a.subject_id = s.id
            LEFT JOIN subject_teachers st_link ON s.id = st_link.subject_id
            LEFT JOIN teachers t ON st_link.teacher_id = t.id
            LEFT JOIN submissions sub ON sub.assignment_id = a.id AND sub.student_id = ?
            GROUP BY a.id, s.name
            ORDER BY a.deadline
        """, (student_id_int,))

        assignments = []
        for row in cur.fetchall():
            teachers = row["teachers"]
            # Если нет преподавателей — покажем "—"
            if not teachers or teachers == "NULL":
                teachers = "—"

            assignments.append({
                "id": row["id"],
                "subject": row["subject"],
                "teachers": teachers,  # ← добавлено
                "title": row["title"],
                "description": row["description"],
                "deadline": row["deadline"],
                "submitted": False  # мы не проверяем submitted здесь — оставим как раньше
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
    
@app.post("/api/teacher/login")
async def teacher_login(teacher_id: str = Form(...)):
    with get_db() as conn:
        cur = conn.execute("""
            SELECT id, last_name, first_name, patronymic
            FROM teachers
            WHERE teacher_id = ?
        """, (teacher_id.strip(),))
        teacher = cur.fetchone()
        if not teacher:
            raise HTTPException(404, "Преподаватель не найден")
        return dict(teacher)

@app.get("/api/teacher/assignments/{teacher_id}")
async def get_teacher_assignments(teacher_id: str):
    with get_db() as conn:
        # Получаем ID преподавателя
        cur = conn.execute("SELECT id FROM teachers WHERE teacher_id = ?", (teacher_id,))
        teacher_row = cur.fetchone()
        if not teacher_row:
            raise HTTPException(404, "Преподаватель не найден")
        teacher_id_int = teacher_row[0]

        # Получаем все задания по его предметам + отправленные работы
        cur = conn.execute("""
            SELECT
                a.id AS assignment_id,
                a.title,
                a.deadline,
                s.name AS subject,
                st.last_name || ' ' || st.first_name AS student_name,
                st.student_id,
                sub.file_path,
                sub.submitted_at,
                gr.grade,
                gr.status
            FROM assignments a
            JOIN subjects s ON a.subject_id = s.id
            JOIN subject_teachers st_link ON s.id = st_link.subject_id
            JOIN students st ON st.id IN (
                SELECT DISTINCT student_id FROM submissions WHERE assignment_id = a.id
            )
            LEFT JOIN submissions sub ON sub.assignment_id = a.id AND sub.student_id = st.id
            LEFT JOIN grades gr ON gr.student_id = st.id AND gr.subject_id = s.id
            WHERE st_link.teacher_id = ?
            ORDER BY a.deadline DESC, st.last_name
        """, (teacher_id_int,))

        assignments = [dict(row) for row in cur.fetchall()]
        return assignments
    
@app.post("/api/teacher/grade")
async def set_grade(
    student_id: str = Form(...),
    subject_name: str = Form(...),
    grade: Optional[int] = Form(None),
    status: str = Form("не сдано")
):
    with get_db() as conn:
        # Получаем ID студента
        cur = conn.execute("SELECT id FROM students WHERE student_id = ?", (student_id,))
        student_row = cur.fetchone()
        if not student_row:
            raise HTTPException(404, "Студент не найден")
        student_id_int = student_row[0]

        # Получаем ID предмета
        cur = conn.execute("SELECT id FROM subjects WHERE name = ?", (subject_name,))
        subject_row = cur.fetchone()
        if not subject_row:
            raise HTTPException(404, "Предмет не найден")
        subject_id_int = subject_row[0]

        # Обновляем или вставляем оценку
        conn.execute("""
            INSERT INTO grades (student_id, subject_id, grade, status)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(student_id, subject_id)
            DO UPDATE SET grade = excluded.grade, status = excluded.status
        """, (student_id_int, subject_id_int, grade, status))

        return {"message": "Оценка сохранена"}
    
@app.get("/download/{path:path}")
async def download_file(path: str):
    """
    Позволяет скачивать файлы из storage/submissions/...
    Внимание: в продакшене нужна авторизация!
    """
    # Убедимся, что путь не начинается с "../" — защита от path traversal
    if ".." in path or path.startswith("/"):
        raise HTTPException(400, "Некорректный путь")

    full_path = os.path.join("storage", path)
    if not os.path.exists(full_path):
        raise HTTPException(404, "Файл не найден")
    return FileResponse(full_path)

@app.get("/teacher")
async def teacher_page():
    with open("static/teacher.html", encoding="utf-8") as f:
        return HTMLResponse(f.read())