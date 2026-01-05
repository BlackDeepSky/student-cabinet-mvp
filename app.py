"""
Личный кабинет заочного студента — MVP
Backend на FastAPI + SQLite
"""

import sqlite3
import os
import shutil
from pathlib import Path
from datetime import datetime
from fastapi import FastAPI, File, UploadFile, HTTPException, Form
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from typing import Optional

# Конфигурация
DB_PATH = "instance/app.db"
UPLOAD_BASE_DIR = "storage/submissions"

# Убедимся, что папки существуют
Path("instance").mkdir(exist_ok=True)
Path(UPLOAD_BASE_DIR).mkdir(parents=True, exist_ok=True)

# Вспомогательная функция подключения к БД
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Позволяет обращаться по имени колонки
    return conn

# Создаём приложение
app = FastAPI()

# Раздаём статические файлы
app.mount("/static", StaticFiles(directory="static"), name="static")

# Главная страница — редирект на студента
@app.get("/", response_class=HTMLResponse)
async def root():
    with open("static/index.html", encoding="utf-8") as f:
        return HTMLResponse(f.read())

# ===== СТУДЕНТ =====

@app.post("/api/login")
async def login(student_id: str = Form(...)):
    """Вход студента по student_id"""
    with get_db() as conn:
        cur = conn.execute("""
            SELECT id, last_name, first_name, patronymic
            FROM students
            WHERE student_id = ?
        """, (student_id.strip(),))
        student = cur.fetchone()
        if not student:
            raise HTTPException(404, "Студент не найден")
        return dict(student)

@app.post("/api/submit/{assignment_id}")
async def submit_work(
    assignment_id: int,
    student_id: str = Form(...),
    files: list[UploadFile] = File(...)
):
    """Отправка нескольких файлов на задание"""
    if not files or all(f.filename == "" for f in files):
        raise HTTPException(400, "Не выбраны файлы")

    with get_db() as conn:
        # ID студента
        cur = conn.execute("SELECT id FROM students WHERE student_id = ?", (student_id,))
        student_row = cur.fetchone()
        if not student_row:
            raise HTTPException(404, "Студент не найден")
        student_id_int = student_row[0]

        # Проверка задания
        cur = conn.execute("SELECT id FROM assignments WHERE id = ?", (assignment_id,))
        if not cur.fetchone():
            raise HTTPException(404, "Задание не найдено")

        # Создаём запись работы
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

        # Сохраняем файлы
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

            # Сохраняем в submission_files
            conn.execute("""
                INSERT INTO submission_files (submission_id, file_path)
                VALUES (?, ?)
            """, (submission_id, file_path))

        return {"message": f"Отправлено {len(files)} файлов"}

@app.get("/api/assignments/{student_id}")
async def get_assignments(student_id: str):
    """Получить задания студента со статусами и преподавателями"""
    with get_db() as conn:
        cur = conn.execute("SELECT id FROM students WHERE student_id = ?", (student_id,))
        student_row = cur.fetchone()
        if not student_row:
            raise HTTPException(404, "Студент не найден")
        student_id_int = student_row[0]

        # Все задания
        cur = conn.execute("""
            SELECT a.id, a.title, a.description, a.deadline, s.id AS subject_id, s.name AS subject
            FROM assignments a
            JOIN subjects s ON a.subject_id = s.id
            ORDER BY a.deadline
        """)
        assignments_raw = cur.fetchall()

        # Статусы работ
        cur = conn.execute("""
            SELECT assignment_id, status, submitted_at, review
            FROM submissions
            WHERE student_id = ?
        """, (student_id_int,))
        submission_map = {}
        for row in cur.fetchall():
            submission_map[row["assignment_id"]] = {
                "status": row["status"],
                "submitted_at": row["submitted_at"],
                "review": row["review"]
            }

        # Преподаватели по предметам
        cur = conn.execute("""
            SELECT s.id AS subject_id,
                   GROUP_CONCAT(
                       t.last_name || ' ' || substr(t.first_name, 1, 1) || '.' ||
                       CASE WHEN t.patronymic IS NOT NULL 
                           THEN substr(t.patronymic, 1, 1) || '.' 
                           ELSE '' END,
                       ', '
                   ) AS teachers
            FROM subjects s
            JOIN subject_teachers st_link ON s.id = st_link.subject_id
            JOIN teachers t ON st_link.teacher_id = t.id
            GROUP BY s.id
        """)
        teacher_map = {row["subject_id"]: row["teachers"] for row in cur.fetchall()}

        # Сборка
        assignments = []
        for a in assignments_raw:
            subject_id = a["subject_id"]
            teachers = teacher_map.get(subject_id) or "—"
            sub = submission_map.get(a["id"]) or {}

            assignments.append({
                "id": a["id"],
                "subject": a["subject"],
                "teachers": teachers,
                "title": a["title"],
                "description": a["description"],
                "deadline": a["deadline"],
                "status": sub.get("status"),
                "submitted_at": sub.get("submitted_at"),
                "review": sub.get("review")
            })
        return assignments

@app.get("/api/grades/{student_id}")
async def get_grades(student_id: str):
    """Успеваемость с датой и временем"""
    with get_db() as conn:
        cur = conn.execute("SELECT id FROM students WHERE student_id = ?", (student_id,))
        student_row = cur.fetchone()
        if not student_row:
            raise HTTPException(404, "Студент не найден")
        student_id_int = student_row[0]

        cur = conn.execute("""
            SELECT s.name AS subject, g.grade, g.status, g.graded_at
            FROM grades g
            JOIN subjects s ON g.subject_id = s.id
            WHERE g.student_id = ?
            ORDER BY g.graded_at DESC
        """, (student_id_int,))

        grades = []
        for row in cur.fetchall():
            graded_at = row["graded_at"]
            if graded_at:
                dt = datetime.fromisoformat(graded_at)
                formatted_date = dt.strftime("%d.%m.%Y, %H:%M")
            else:
                formatted_date = "—"
            grades.append({
                "subject": row["subject"],
                "grade": row["grade"],
                "status": row["status"],
                "graded_at": formatted_date
            })
        return grades

# ===== ПРЕПОДАВАТЕЛЬ =====

@app.post("/api/teacher/login")
async def teacher_login(teacher_id: str = Form(...)):
    """Вход преподавателя"""
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
    """Работы студентов по предметам преподавателя"""
    with get_db() as conn:
        cur = conn.execute("SELECT id FROM teachers WHERE teacher_id = ?", (teacher_id,))
        teacher_row = cur.fetchone()
        if not teacher_row:
            raise HTTPException(404, "Преподаватель не найден")
        teacher_id_int = teacher_row[0]

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

        return [dict(row) for row in cur.fetchall()]

@app.get("/api/teacher/files/{assignment_id}/{student_id}")
async def get_submission_files(assignment_id: int, student_id: str):
    """Получить список файлов работы"""
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

@app.post("/api/teacher/grade")
async def set_grade(
    student_id: str = Form(...),
    subject_name: str = Form(...),
    assignment_id: int = Form(...),
    status_input: str = Form(...),
    review: Optional[str] = Form(None)
):
    """Выставить оценку/статус и сохранить рецензию"""
    with get_db() as conn:
        # ID студента
        cur = conn.execute("SELECT id FROM students WHERE student_id = ?", (student_id,))
        student_row = cur.fetchone()
        if not student_row:
            raise HTTPException(404, "Студент не найден")
        student_id_int = student_row[0]

        # ID предмета
        cur = conn.execute("SELECT id FROM subjects WHERE name = ?", (subject_name,))
        subject_row = cur.fetchone()
        if not subject_row:
            raise HTTPException(404, "Предмет не найден")
        subject_id_int = subject_row[0]

        # Статус для submissions
        status_mapping = {
            "зачёт": "approved",
            "сдано": "approved",
            "не зачтено": "rejected",
            "не допущен": "rejected",
            "не сдано": "rejected",
            "принят на рассмотрение": "in_review"
        }
        db_status = status_mapping.get(status_input, "submitted")

        # Обновляем submissions
        conn.execute("""
            UPDATE submissions
            SET status = ?, review = ?
            WHERE student_id = ? AND assignment_id = ?
        """, (db_status, review, student_id_int, assignment_id))

        # Обновляем grades с датой
        grade_value = 100 if status_input in ("зачёт", "сдано") else None

        conn.execute("""
            INSERT INTO grades (student_id, subject_id, grade, status, review, graded_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(student_id, subject_id)
            DO UPDATE SET 
                grade = excluded.grade,
                status = excluded.status,
                review = excluded.review,
                graded_at = excluded.graded_at
        """, (student_id_int, subject_id_int, grade_value, status_input, review))

        return {"message": "Статус и рецензия сохранены"}

# ===== СКАЧИВАНИЕ ФАЙЛОВ =====

@app.get("/download/{path:path}")
async def download_file(path: str):
    """Скачивание файла с принудительным сохранением"""
    if ".." in path or path.startswith("/"):
        raise HTTPException(400, "Некорректный путь")

    full_path = os.path.join("storage", path)
    if not os.path.exists(full_path):
        raise HTTPException(404, "Файл не найден")

    original_name = os.path.basename(path)
    return FileResponse(
        full_path,
        filename=original_name,
        media_type='application/octet-stream'
    )

# Страница преподавателя
@app.get("/teacher", response_class=HTMLResponse)
async def teacher_page():
    with open("static/teacher.html", encoding="utf-8") as f:
        return HTMLResponse(f.read())