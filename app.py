"""
Личный кабинет заочного студента — MVP
Backend на FastAPI + SQLite
"""

import sqlite3
import os
import shutil
import re
from pathlib import Path
from datetime import datetime
from fastapi import FastAPI, File, UploadFile, HTTPException, Form
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from typing import Optional
from datetime import datetime

# === Константы ===
DB_PATH = Path("instance/app.db")
UPLOAD_BASE_DIR = Path("storage/submissions")
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 МБ
VALID_ID_PATTERN = re.compile(r"^[A-Za-z0-9\-_]+$")

# Убедимся, что папки существуют
DB_PATH.parent.mkdir(exist_ok=True)
UPLOAD_BASE_DIR.mkdir(parents=True, exist_ok=True)

# === Безопасная инициализация БД ===
def init_database_if_needed():
    if not DB_PATH.exists():
        print("БД отсутствует. Инициализирую...")
        try:
            from seed_data import seed_data
            seed_data()
            print("БД успешно создана.")
        except Exception as e:
            print(f"Ошибка при инициализации БД: {e}")
            # Не падаем — даём серверу запуститься (но без данных)
            # В продакшене можно raise, но для MVP — безопаснее продолжить

init_database_if_needed()

# === Вспомогательные функции ===
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def sanitize_filename(filename: str) -> str:
    """Очистка имени файла от потенциально опасных символов"""
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in filename)
    return safe[:100]  # Ограничение длины

def validate_id(user_id: str) -> str:
    """Проверка корректности ID студента/преподавателя"""
    id_clean = user_id.strip()
    if not id_clean or not VALID_ID_PATTERN.match(id_clean):
        raise HTTPException(400, "Некорректный идентификатор")
    return id_clean

def normalize_birth_date(raw: str) -> Optional[str]:
    """
    Преобразует ввод пользователя в формат YYYY-MM-DD.
    Поддерживаемые форматы: ДД.ММ.ГГГГ, ДДММГГГГ, ДД-ММ-ГГГГ
    Возвращает None, если формат неверный.
    """
    if not raw:
        return None
    raw = re.sub(r"[^\d]", "", raw.strip())  # оставляем только цифры
    if len(raw) == 8:  # ДДММГГГГ
        day, month, year = raw[:2], raw[2:4], raw[4:]
    elif len(raw) == 6:  # ДДММГГ → предполагаем 19 или 20 век
        day, month, year = raw[:2], raw[2:4], "20" + raw[4:] if int(raw[4:]) <= 25 else "19" + raw[4:]
    else:
        return None

    # Проверка валидности даты
    try:
        dt = datetime(int(year), int(month), int(day))
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        return None

# === Приложение ===
app = FastAPI()

# Раздаём статические файлы
app.mount("/static", StaticFiles(directory="static"), name="static")

# Главная страница
@app.get("/", response_class=HTMLResponse)
async def root():
    with open("static/index.html", encoding="utf-8") as f:
        return HTMLResponse(f.read())

# Страница преподавателя
@app.get("/teacher", response_class=HTMLResponse)
async def teacher_page():
    with open("static/teacher.html", encoding="utf-8") as f:
        return HTMLResponse(f.read())

# ===== СТУДЕНТ =====

@app.post("/api/login")
async def login(student_id: str = Form(...), password: str = Form(...)):
    """Вход студента по student_id и дате рождения"""
    clean_id = validate_id(student_id)
    birth_date = normalize_birth_date(password)
    if not birth_date:
        raise HTTPException(400, "Неверный формат даты рождения. Используйте ДД.ММ.ГГГГ")

    with get_db() as conn:
        cur = conn.execute("""
            SELECT id, last_name, first_name, patronymic
            FROM students
            WHERE student_id = ? AND birth_date = ?
        """, (clean_id, birth_date))
        student = cur.fetchone()
        if not student:
            raise HTTPException(401, "Неверный номер студенческого или дата рождения")
        return dict(student)

@app.post("/api/submit/{assignment_id}")
async def submit_work(
    assignment_id: int,
    student_id: str = Form(...),
    files: list[UploadFile] = File(...)
):
    if not files or all(f.filename == "" for f in files):
        raise HTTPException(400, "Не выбраны файлы")

    clean_id = validate_id(student_id)
    with get_db() as conn:
        # Проверка студента
        cur = conn.execute("SELECT id FROM students WHERE student_id = ?", (clean_id,))
        student_row = cur.fetchone()
        if not student_row:
            raise HTTPException(404, "Студент не найден")
        student_id_int = student_row[0]

        # Проверка задания
        cur = conn.execute("SELECT id FROM assignments WHERE id = ?", (assignment_id,))
        if not cur.fetchone():
            raise HTTPException(404, "Задание не найдено")

        # Создаём запись работы (без commit — контекст сам управляет)
        conn.execute("""
            INSERT OR IGNORE INTO submissions (student_id, assignment_id)
            VALUES (?, ?)
        """, (student_id_int, assignment_id))

        # Получаем ID работы
        cur = conn.execute("""
            SELECT id FROM submissions WHERE student_id = ? AND assignment_id = ?
        """, (student_id_int, assignment_id))
        submission_id = cur.fetchone()[0]

        # Сохраняем файлы
        file_dir = UPLOAD_BASE_DIR / str(student_id_int) / str(assignment_id)
        file_dir.mkdir(parents=True, exist_ok=True)  # Один раз

        saved_count = 0
        for file in files:
            if not file.filename:
                continue

            # Проверка размера
            if file.size > MAX_FILE_SIZE:
                raise HTTPException(400, f"Файл {file.filename} слишком большой (макс. 10 МБ)")

            safe_name = sanitize_filename(file.filename)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{timestamp}_{safe_name}"
            file_path = file_dir / filename

            # Запись файла
            with open(file_path, "wb") as f:
                shutil.copyfileobj(file.file, f)

            # Сохраняем в БД
            conn.execute("""
                INSERT INTO submission_files (submission_id, file_path)
                VALUES (?, ?)
            """, (submission_id, str(file_path)))
            saved_count += 1

        return {"message": f"Отправлено {saved_count} файлов"}

@app.get("/api/assignments/{student_id}")
async def get_assignments(student_id: str):
    clean_id = validate_id(student_id)
    with get_db() as conn:
        cur = conn.execute("SELECT id FROM students WHERE student_id = ?", (clean_id,))
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
        submission_map = {
            row["assignment_id"]: {
                "status": row["status"],
                "submitted_at": row["submitted_at"],
                "review": row["review"]
            }
            for row in cur.fetchall()
        }

        # Преподаватели
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
        teacher_map = {row["subject_id"]: row["teachers"] or "—" for row in cur.fetchall()}

        # Сборка
        return [
            {
                "id": a["id"],
                "subject": a["subject"],
                "teachers": teacher_map.get(a["subject_id"], "—"),
                "title": a["title"],
                "description": a["description"],
                "deadline": a["deadline"],
                "status": submission_map.get(a["id"], {}).get("status"),
                "submitted_at": submission_map.get(a["id"], {}).get("submitted_at"),
                "review": submission_map.get(a["id"], {}).get("review")
            }
            for a in assignments_raw
        ]

@app.get("/api/grades/{student_id}")
async def get_grades(student_id: str):
    clean_id = validate_id(student_id)
    with get_db() as conn:
        cur = conn.execute("SELECT id FROM students WHERE student_id = ?", (clean_id,))
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
            formatted_date = "—"
            if graded_at:
                try:
                    dt = datetime.fromisoformat(graded_at)
                    formatted_date = dt.strftime("%d.%m.%Y, %H:%M")
                except ValueError:
                    pass
            grades.append({
                "subject": row["subject"],
                "grade": row["grade"],
                "status": row["status"],
                "graded_at": formatted_date
            })
        return grades

# ===== ПРЕПОДАВАТЕЛЬ =====

@app.post("/api/teacher/login")
async def teacher_login(teacher_id: str = Form(...), password: str = Form(...)):
    """Вход преподавателя по teacher_id и дате рождения"""
    clean_id = validate_id(teacher_id)
    birth_date = normalize_birth_date(password)
    if not birth_date:
        raise HTTPException(400, "Неверный формат даты рождения. Используйте ДД.ММ.ГГГГ")

    with get_db() as conn:
        cur = conn.execute("""
            SELECT id, last_name, first_name, patronymic
            FROM teachers
            WHERE teacher_id = ? AND birth_date = ?
        """, (clean_id, birth_date))
        teacher = cur.fetchone()
        if not teacher:
            raise HTTPException(401, "Неверный ID преподавателя или дата рождения")
        return dict(teacher)

@app.get("/api/teacher/assignments/{teacher_id}")
async def get_teacher_assignments(teacher_id: str):
    clean_id = validate_id(teacher_id)
    with get_db() as conn:
        cur = conn.execute("SELECT id FROM teachers WHERE teacher_id = ?", (clean_id,))
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
    clean_id = validate_id(student_id)
    with get_db() as conn:
        cur = conn.execute("""
            SELECT sf.file_path
            FROM submission_files sf
            JOIN submissions s ON sf.submission_id = s.id
            JOIN students st ON s.student_id = st.id
            WHERE s.assignment_id = ? AND st.student_id = ?
        """, (assignment_id, clean_id))
        return [
            {
                "path": row[0].replace("storage/", "", 1),
                "name": os.path.basename(row[0])
            }
            for row in cur.fetchall()
        ]

@app.post("/api/teacher/grade")
async def set_grade(
    student_id: str = Form(...),
    subject_name: str = Form(...),
    assignment_id: int = Form(...),
    status_input: str = Form(...),
    review: Optional[str] = Form(None)
):
    clean_student_id = validate_id(student_id)
    with get_db() as conn:
        # ID студента
        cur = conn.execute("SELECT id FROM students WHERE student_id = ?", (clean_student_id,))
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

        # Удаление файлов при "не зачтено"
        if status_input == "не зачтено":
            cur = conn.execute("""
                SELECT s.id FROM submissions s
                WHERE s.student_id = ? AND s.assignment_id = ?
            """, (student_id_int, assignment_id))
            submission_row = cur.fetchone()
            if submission_row:
                submission_id = submission_row[0]
                cur = conn.execute("SELECT file_path FROM submission_files WHERE submission_id = ?", (submission_id,))
                file_paths = [row[0] for row in cur.fetchall()]

                # Удаляем файлы
                for fp in file_paths:
                    try:
                        os.remove(fp)
                    except (FileNotFoundError, OSError):
                        pass  # Игнорируем ошибки удаления

                # Удаляем записи
                conn.execute("DELETE FROM submission_files WHERE submission_id = ?", (submission_id,))

        # Обновление статуса
        status_mapping = {
            "зачёт": "approved",
            "сдано": "approved",
            "не зачтено": "rejected",
            "не допущен": "rejected",
            "не сдано": "rejected",
            "принят на рассмотрение": "in_review"
        }
        db_status = status_mapping.get(status_input, "submitted")

        conn.execute("""
            UPDATE submissions
            SET status = ?, review = ?
            WHERE student_id = ? AND assignment_id = ?
        """, (db_status, review, student_id_int, assignment_id))

        # Обновление итоговой таблицы
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
    # Защита от path traversal
    if ".." in path or path.startswith("/"):
        raise HTTPException(400, "Некорректный путь")

    full_path = Path("storage") / path
    if not full_path.is_file():
        raise HTTPException(404, "Файл не найден")

    # Дополнительная защита: убедимся, что путь внутри storage
    try:
        full_path = full_path.resolve().relative_to(Path("storage").resolve())
        full_path = Path("storage") / full_path
    except ValueError:
        raise HTTPException(400, "Доступ запрещён")

    return FileResponse(
        full_path,
        filename=full_path.name,
        media_type='application/octet-stream'
    )