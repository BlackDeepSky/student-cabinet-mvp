"""
Личный кабинет заочного студента — MVP
Backend на FastAPI + SQLite
"""

import sqlite3
import os
import shutil
import re
import secrets
from datetime import timedelta, datetime
from pathlib import Path
from fastapi import FastAPI, File, UploadFile, HTTPException, Form, Depends, Header
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from typing import Optional
from fastapi.middleware.cors import CORSMiddleware
import bcrypt as _bcrypt


def verify_password(password: str, hashed: str) -> bool:
    return _bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))

# === Вспомогательные функции для времени ===
def get_current_time():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

# === Константы ===
DB_PATH = Path("instance/app.db")
UPLOAD_BASE_DIR = Path("storage/submissions")
FEEDBACK_DIR = Path("storage/feedback")
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 МБ
VALID_ID_PATTERN = re.compile(r"^[A-Za-z0-9\-_]+$")
SESSION_EXPIRE_HOURS = 24

# Убедимся, что папки существуют
DB_PATH.parent.mkdir(exist_ok=True)
UPLOAD_BASE_DIR.mkdir(parents=True, exist_ok=True)
FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)

# === Безопасная инициализация БД ===
def init_database_if_needed():
    if not DB_PATH.exists():
        print("🔵 БД отсутствует. Инициализирую...")
        try:
            from db_seed import seed_data
            seed_data()
            print("✅ БД успешно создана.")
        except Exception as e:
            print(f"❌ Ошибка при инициализации БД: {e}")

init_database_if_needed()

# === Вспомогательные функции ===
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def sanitize_filename(filename: str) -> str:
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in filename)
    return safe[:100]

def validate_id(user_id: str) -> str:
    id_clean = user_id.strip()
    if not id_clean or not VALID_ID_PATTERN.match(id_clean):
        raise HTTPException(400, "Некорректный идентификатор")
    return id_clean

def create_session(user_id: int, user_type: str) -> str:
    token = secrets.token_urlsafe(32)
    expires_at = (datetime.now() + timedelta(hours=SESSION_EXPIRE_HOURS)).strftime('%Y-%m-%d %H:%M:%S')
    
    with get_db() as conn:
        conn.execute("DELETE FROM sessions WHERE user_id = ? AND user_type = ?", (user_id, user_type))
        conn.execute("""
            INSERT INTO sessions (token, user_id, user_type, expires_at)
            VALUES (?, ?, ?, ?)
        """, (token, user_id, user_type, expires_at))
    return token

def verify_session(token: str):
    if not token:
        return None
    
    current_time = get_current_time()
    with get_db() as conn:
        cur = conn.execute("SELECT user_id, user_type, expires_at FROM sessions WHERE token = ?", (token,))
        row = cur.fetchone()
        if not row:
            return None
        
        user_id, user_type, expires_at = row
        if expires_at <= current_time:
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
            return None
        
        return (user_id, user_type)

async def require_auth(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Требуется авторизация")
    
    token = authorization.split(" ", 1)[1]
    session = verify_session(token)
    if not session:
        raise HTTPException(401, "Неверный или просроченный токен")
    return session

# === Приложение ===
app = FastAPI()

# Настройка CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "http://127.0.0.1:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Подключение статики
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", response_class=HTMLResponse)
async def root():
    with open("static/index.html", encoding="utf-8") as f:
        return HTMLResponse(f.read())

@app.get("/teacher", response_class=HTMLResponse)
async def teacher_page():
    with open("static/teacher.html", encoding="utf-8") as f:
        return HTMLResponse(f.read())

# ===== СТУДЕНТ =====

@app.post("/api/login")
async def login(student_id: str = Form(...), password: str = Form(...)):
    clean_id = validate_id(student_id)

    with get_db() as conn:
        cur = conn.execute("""
            SELECT id, last_name, first_name, patronymic, password_hash
            FROM students
            WHERE student_id = ?
        """, (clean_id,))
        student = cur.fetchone()
        if not student or not verify_password(password, student["password_hash"]):
            raise HTTPException(401, "Неверный номер студенческого или пароль")

        token = create_session(student["id"], "student")
        user = {k: student[k] for k in ("id", "last_name", "first_name", "patronymic")}
        return {
            "token": token,
            "user": user
        }

@app.post("/api/submit/{assignment_id}")
async def submit_work(
    assignment_id: int,
    files: list[UploadFile] = File(...),
    session = Depends(require_auth)
):
    user_id, user_type = session
    if user_type != "student":
        raise HTTPException(403, "Доступ запрещён")
    
    if not files or all(f.filename == "" for f in files):
        raise HTTPException(400, "Не выбраны файлы")

    with get_db() as conn:
        cur = conn.execute("SELECT id FROM assignments WHERE id = ?", (assignment_id,))
        if not cur.fetchone():
            raise HTTPException(404, "Задание не найдено")

        # Создаём запись, если её нет
        conn.execute("""
            INSERT OR IGNORE INTO submissions (student_id, assignment_id, status)
            VALUES (?, ?, 'submitted')
        """, (user_id, assignment_id))

        # Получаем текущий статус
        cur = conn.execute("""
            SELECT id, status FROM submissions 
            WHERE student_id = ? AND assignment_id = ?
        """, (user_id, assignment_id))
        submission_row = cur.fetchone()
        submission_id = submission_row[0]
        current_status = submission_row[1]

        # Определяем новый статус
        new_status = "submitted"
        if current_status == "rejected":
            new_status = "resubmitted"

        # Обновляем статус и время
        conn.execute("""
            UPDATE submissions
            SET status = ?, submitted_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (new_status, submission_id))

        # Сохраняем файлы
        file_dir = UPLOAD_BASE_DIR / str(user_id) / str(assignment_id)
        file_dir.mkdir(parents=True, exist_ok=True)
        saved_count = 0
        for file in files:
            if not file.filename:
                continue
            if file.size > MAX_FILE_SIZE:
                raise HTTPException(400, f"Файл {file.filename} слишком большой (макс. 10 МБ)")
            safe_name = sanitize_filename(file.filename)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{timestamp}_{safe_name}"
            file_path = file_dir / filename
            with open(file_path, "wb") as f:
                shutil.copyfileobj(file.file, f)
            conn.execute("""
                INSERT INTO submission_files (submission_id, file_path)
                VALUES (?, ?)
            """, (submission_id, str(file_path)))
            saved_count += 1

        return {"message": f"Отправлено {saved_count} файлов"}

# Эндпоинты для студентов (/me)
@app.get("/api/assignments/me")
async def get_my_assignments(session = Depends(require_auth)):
    user_id, user_type = session
    if user_type != "student":
        raise HTTPException(403, "Доступ запрещён")
    
    with get_db() as conn:
        cur = conn.execute("""
            SELECT a.id, a.title, a.description, a.deadline, s.id AS subject_id, s.name AS subject
            FROM assignments a
            JOIN subjects s ON a.subject_id = s.id
            JOIN student_subjects ss ON s.id = ss.subject_id
            WHERE ss.student_id = ?
            ORDER BY a.deadline
        """, (user_id,))
        assignments_raw = cur.fetchall()

        # Получаем все ID заданий
        all_assignment_ids = [a["id"] for a in assignments_raw]

        # Получаем статусы и submission_id
        cur = conn.execute("""
            SELECT id, assignment_id, status, submitted_at, review
            FROM submissions
            WHERE student_id = ?
        """, (user_id,))
        submission_map = {}
        for row in cur.fetchall():
            submission_map[row["assignment_id"]] = {
                "submission_id": row["id"],
                "status": row["status"],
                "submitted_at": row["submitted_at"],
                "review": row["review"]
            }

        # Гарантируем, что каждое задание есть в мапе
        for aid in all_assignment_ids:
            if aid not in submission_map:
                submission_map[aid] = {
                    "submission_id": None,
                    "status": None,
                    "submitted_at": None,
                    "review": None
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
        teacher_map = {row["subject_id"]: row["teachers"] or "—" for row in cur.fetchall()}
        
        # Проверяем наличие файлов от преподавателя
        submission_ids = [v["submission_id"] for v in submission_map.values() if v["submission_id"]]
        has_feedback = set()
        if submission_ids:
            placeholders = ','.join('?' * len(submission_ids))
            cur = conn.execute(f"""
                SELECT submission_id FROM teacher_feedback_files
                WHERE submission_id IN ({placeholders})
            """, submission_ids)
            has_feedback = {row[0] for row in cur.fetchall()}

        # Маппинг статусов
        STATUS_LABELS = {
            "submitted": "Отправлено",
            "in_review": "На рассмотрении",
            "approved": "Зачтено",
            "rejected": "Не зачтено",
            "resubmitted": "Не зачтено (повторно отправлена)"
        }

        return [
            {
                "id": a["id"],
                "subject": a["subject"],
                "teachers": teacher_map.get(a["subject_id"], "—"),
                "title": a["title"],
                "description": a["description"],
                "deadline": a["deadline"],
                "status": submission_map[a["id"]]["status"],
                "status_label": STATUS_LABELS.get(submission_map[a["id"]]["status"], "Не отправлено"),
                "submitted_at": submission_map[a["id"]]["submitted_at"],
                "review": submission_map[a["id"]]["review"],
                "submission_id": submission_map[a["id"]]["submission_id"],
                "has_teacher_feedback": submission_map[a["id"]]["submission_id"] in has_feedback
            }
            for a in assignments_raw
        ]

@app.get("/api/grades/me")
async def get_my_grades(session = Depends(require_auth)):
    user_id, user_type = session
    if user_type != "student":
        raise HTTPException(403, "Доступ запрещён")
    
    with get_db() as conn:
        cur = conn.execute("""
            SELECT s.name AS subject, g.grade, g.status, g.graded_at
            FROM grades g
            JOIN subjects s ON g.subject_id = s.id
            WHERE g.student_id = ?
            ORDER BY g.graded_at DESC
        """, (user_id,))

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
    clean_id = validate_id(teacher_id)

    with get_db() as conn:
        cur = conn.execute("""
            SELECT id, last_name, first_name, patronymic, password_hash
            FROM teachers
            WHERE teacher_id = ?
        """, (clean_id,))
        teacher = cur.fetchone()
        if not teacher or not verify_password(password, teacher["password_hash"]):
            raise HTTPException(401, "Неверный ID преподавателя или пароль")

        token = create_session(teacher["id"], "teacher")
        user = {k: teacher[k] for k in ("id", "last_name", "first_name", "patronymic")}
        return {
            "token": token,
            "user": user
        }

# Эндпоинты для преподавателей (/me)
@app.get("/api/teacher/assignments/me")
async def get_my_teacher_assignments(session = Depends(require_auth)):
    user_id, user_type = session
    if user_type != "teacher":
        raise HTTPException(403, "Доступ запрещён")

    with get_db() as conn:
        cur = conn.execute("""
            SELECT
                a.id AS assignment_id,
                a.title,
                a.deadline,
                s.name AS subject,
                st.last_name || ' ' || st.first_name AS student_name,
                st.student_id,
                sub.submitted_at,
                sub.status AS last_status,
                g.graded_at AS last_action_at
            FROM assignments a
            JOIN subjects s ON a.subject_id = s.id
            JOIN subject_teachers st_link ON s.id = st_link.subject_id
            JOIN submissions sub ON sub.assignment_id = a.id
            JOIN students st ON sub.student_id = st.id
            LEFT JOIN grades g ON g.student_id = st.id AND g.subject_id = s.id
            WHERE st_link.teacher_id = ?
            AND (sub.status IS NULL OR sub.status NOT IN ('approved'))
            ORDER BY a.deadline DESC, st.last_name
        """, (user_id,))
        
        # Маппинг статусов
        STATUS_LABELS = {
            "submitted": "Отправлено",
            "in_review": "На рассмотрении",
            "approved": "Зачтено",
            "rejected": "Не зачтено",
            "resubmitted": "Не зачтено (повторно отправлена)"
        }
        
        result = []
        for row in cur.fetchall():
            result.append({
                "assignment_id": row["assignment_id"],
                "title": row["title"],
                "deadline": row["deadline"],
                "subject": row["subject"],
                "student_name": row["student_name"],
                "student_id": row["student_id"],
                "submitted_at": row["submitted_at"],
                "last_status": row["last_status"],
                "last_status_label": STATUS_LABELS.get(row["last_status"], "—"),
                "last_action_at": row["last_action_at"]
            })
        return result

@app.get("/api/teacher/history/me")
async def get_my_teacher_history(session = Depends(require_auth)):
    user_id, user_type = session
    if user_type != "teacher":
        raise HTTPException(403, "Доступ запрещён")

    with get_db() as conn:
        cur = conn.execute("""
            SELECT
                st.last_name || ' ' || st.first_name AS student_name,
                st.student_id,
                s.name AS subject,
                a.title AS assignment_title,
                g.graded_at,
                a.id AS assignment_id
            FROM grades g
            JOIN subjects s ON g.subject_id = s.id
            JOIN assignments a ON a.subject_id = s.id
            JOIN students st ON g.student_id = st.id
            JOIN subject_teachers st_link ON s.id = st_link.subject_id
            WHERE st_link.teacher_id = ?
              AND g.status IN ('зачёт', 'сдано')
            ORDER BY g.graded_at DESC
        """, (user_id,))
        return [dict(row) for row in cur.fetchall()]

@app.get("/api/teacher/files/{assignment_id}/{student_id}")
async def get_submission_files(
    assignment_id: int, 
    student_id: str,
    session = Depends(require_auth)
):
    user_id, user_type = session
    if user_type != "teacher":
        raise HTTPException(403, "Доступ запрещён")
    
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
    review: Optional[str] = Form(None),
    session = Depends(require_auth)
):
    user_id, user_type = session
    if user_type != "teacher":
        raise HTTPException(403, "Доступ запрещён")
    
    clean_student_id = validate_id(student_id)
    with get_db() as conn:
        cur = conn.execute("SELECT id FROM students WHERE student_id = ?", (clean_student_id,))
        student_row = cur.fetchone()
        if not student_row:
            raise HTTPException(404, "Студент не найден")
        student_id_int = student_row[0]

        cur = conn.execute("SELECT id FROM subjects WHERE name = ?", (subject_name,))
        subject_row = cur.fetchone()
        if not subject_row:
            raise HTTPException(404, "Предмет не найден")
        subject_id_int = subject_row[0]

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
                for fp in file_paths:
                    try:
                        os.remove(fp)
                    except (FileNotFoundError, OSError):
                        pass
                conn.execute("DELETE FROM submission_files WHERE submission_id = ?", (submission_id,))

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

# ===== ФАЙЛЫ ОБРАТНОЙ СВЯЗИ ОТ ПРЕПОДАВАТЕЛЯ =====

@app.post("/api/teacher/feedback/{assignment_id}/{student_id}")
async def upload_feedback_file(
    assignment_id: int,
    student_id: str,
    file: UploadFile = File(...),
    session = Depends(require_auth)
):
    user_id, user_type = session
    if user_type != "teacher":
        raise HTTPException(403, "Доступ запрещён")
    
    clean_student_id = validate_id(student_id)
    if not file.filename:
        raise HTTPException(400, "Файл не выбран")
    
    if file.size > MAX_FILE_SIZE:
        raise HTTPException(400, f"Файл слишком большой (макс. 10 МБ)")

    with get_db() as conn:
        # Проверяем, что преподаватель ведёт этот предмет у этого студента
        cur = conn.execute("""
            SELECT s.id
            FROM submissions s
            JOIN assignments a ON s.assignment_id = a.id
            JOIN subjects subj ON a.subject_id = subj.id
            JOIN subject_teachers st ON subj.id = st.subject_id
            JOIN students stud ON s.student_id = stud.id
            WHERE s.assignment_id = ? AND stud.student_id = ? AND st.teacher_id = ?
        """, (assignment_id, clean_student_id, user_id))
        submission_row = cur.fetchone()
        if not submission_row:
            raise HTTPException(403, "Нет доступа к этой работе")
        
        submission_id = submission_row[0]

        # Сохраняем файл
        feedback_dir = FEEDBACK_DIR / str(clean_student_id) / str(assignment_id)
        feedback_dir.mkdir(parents=True, exist_ok=True)

        safe_name = sanitize_filename(file.filename)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{safe_name}"
        file_path = feedback_dir / filename

        with open(file_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        # Сохраняем в БД
        conn.execute("""
            INSERT INTO teacher_feedback_files (submission_id, file_path)
            VALUES (?, ?)
        """, (submission_id, str(file_path)))

        return {"message": "Файл комментария сохранён"}

@app.get("/api/download/feedback/{submission_id}")
async def download_feedback_file(submission_id: int, session = Depends(require_auth)):
    user_id, user_type = session
    if user_type != "student":
        raise HTTPException(403, "Доступ запрещён")
    
    with get_db() as conn:
        cur = conn.execute("""
            SELECT tf.file_path, s.student_id
            FROM teacher_feedback_files tf
            JOIN submissions s ON tf.submission_id = s.id
            WHERE tf.submission_id = ?
        """, (submission_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Файл не найден")
        
        file_path, student_id = row
        if student_id != user_id:
            raise HTTPException(403, "Нет доступа к этому файлу")
        
        full_path = Path(file_path)
        if not full_path.is_file():
            raise HTTPException(404, "Файл удалён")
        
        return FileResponse(full_path, filename=full_path.name)

# ===== СКАЧИВАНИЕ ФАЙЛОВ =====

@app.get("/download/{path:path}")
async def download_file(path: str, session = Depends(require_auth)):
    if ".." in path or path.startswith("/"):
        raise HTTPException(400, "Некорректный путь")
    full_path = Path("storage") / path
    if not full_path.is_file():
        raise HTTPException(404, "Файл не найден")
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