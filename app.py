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
    files: list[UploadFile] = File(...)  # ← теперь список!
):
    if not files or all(f.filename == "" for f in files):
        raise HTTPException(400, "Не выбраны файлы")

    with get_db() as conn:
        # Найдём ID студента
        cur = conn.execute("SELECT id FROM students WHERE student_id = ?", (student_id,))
        student_row = cur.fetchone()
        if not student_row:
            raise HTTPException(404, "Студент не найден")
        student_id_int = student_row[0]

        # Проверим задание
        cur = conn.execute("SELECT id FROM assignments WHERE id = ?", (assignment_id,))
        if not cur.fetchone():
            raise HTTPException(404, "Задание не найдено")

        # Создаём запись работы (если ещё нет)
        cur = conn.execute("""
            INSERT OR IGNORE INTO submissions (student_id, assignment_id)
            VALUES (?, ?)
        """, (student_id_int, assignment_id))
        conn.commit()

        # Получаем ID работы
        cur = conn.execute("""
            SELECT id FROM submissions WHERE student_id = ? AND assignment_id = ?
        """, (student_id_int, assignment_id))
        submission_id = cur.fetchone()[0]

        # Сохраняем все файлы
        saved_files = []
        for file in files:
            if not file.filename:
                continue
            safe_filename = "".join(c if c.isalnum() or c in "._-" else "_" for c in file.filename)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{timestamp}_{safe_filename}"
            file_dir = os.path.join("storage", "submissions", str(student_id_int), str(assignment_id))
            Path(file_dir).mkdir(parents=True, exist_ok=True)
            file_path = os.path.join(file_dir, filename)
            with open(file_path, "wb") as f:
                shutil.copyfileobj(file.file, f)

            # Сохраняем путь в submission_files
            conn.execute("""
                INSERT INTO submission_files (submission_id, file_path)
                VALUES (?, ?)
            """, (submission_id, file_path))
            saved_files.append(filename)

        return {"message": f"Отправлено {len(saved_files)} файлов", "files": saved_files}
    
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

        # Получаем все работы студентов по предметам, которые ведёт преподаватель
        cur = conn.execute("""
            SELECT
                a.id AS assignment_id,
                a.title,
                a.deadline,
                s.name AS subject,
                st.last_name || ' ' || st.first_name AS student_name,
                st.student_id,
                sub.submitted_at,
                gr.grade,
                gr.status
            FROM assignments a
            JOIN subjects s ON a.subject_id = s.id
            JOIN subject_teachers st_link ON s.id = st_link.subject_id
            JOIN submissions sub ON sub.assignment_id = a.id
            JOIN students st ON sub.student_id = st.id
            LEFT JOIN grades gr ON gr.student_id = st.id AND gr.subject_id = s.id
            WHERE st_link.teacher_id = ?
              AND (gr.status IS NULL OR gr.status != 'зачёт')
            ORDER BY a.deadline DESC, st.last_name
        """, (teacher_id_int,))

        assignments = []
        for row in cur.fetchall():
            assignments.append({
                "assignment_id": row["assignment_id"],
                "subject": row["subject"],
                "title": row["title"],
                "deadline": row["deadline"],
                "student_name": row["student_name"],
                "student_id": row["student_id"],
                "submitted_at": row["submitted_at"],
                "grade": row["grade"],
                "status": row["status"]
            })
        return assignments
    
@app.post("/api/teacher/grade")
async def set_grade(
    student_id: str = Form(...),
    subject_name: str = Form(...),
    grade: Optional[int] = Form(None),
    status: str = Form("не сдано"),
    review: Optional[str] = Form(None)
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

        # Вставляем или обновляем запись в grades
        conn.execute("""
            INSERT INTO grades (student_id, subject_id, grade, status, review)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(student_id, subject_id)
            DO UPDATE SET 
                grade = excluded.grade,
                status = excluded.status,
                review = excluded.review,
                updated_at = CURRENT_TIMESTAMP
        """, (student_id_int, subject_id_int, grade, status, review))

        return {"message": "Оценка и рецензия сохранены"}
    
@app.get("/download/{path:path}")
async def download_file(path: str):
    if ".." in path or path.startswith("/"):
        raise HTTPException(400, "Некорректный путь")

    full_path = os.path.join("storage", path)
    if not os.path.exists(full_path):
        raise HTTPException(404, "Файл не найден")

    # Извлекаем оригинальное имя файла для сохранения
    original_name = os.path.basename(path)
    # Убираем временный timestamp, если хочешь (по желанию)
    # Например: "20260102_104634_report.pdf" → "report.pdf"
    # Но пока оставим как есть

    return FileResponse(
        full_path,
        filename=original_name,  # ← это ключевой параметр
        media_type='application/octet-stream'  # ← заставляет браузер скачивать
    )

@app.get("/teacher")
async def teacher_page():
    with open("static/teacher.html", encoding="utf-8") as f:
        return HTMLResponse(f.read())

@app.get("/api/teacher/files/{assignment_id}/{student_id}")
async def get_submission_files(assignment_id: int, student_id: str):
    with get_db() as conn:
        cur = conn.execute("""
            SELECT sf.file_path
            FROM submission_files sf
            JOIN submissions s ON sf.submission_id = s.id
            JOIN students st ON s.student_id = st.id
            WHERE s.assignment_id = ? AND st.student_id = ?
        """, (assignment_id, student_id))
        files = []
        for row in cur.fetchall():
            path = row[0]
            name = os.path.basename(path)
            files.append({"path": path.replace("storage/", ""), "name": name})
        return files