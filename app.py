"""
Личный кабинет заочного студента — MVP
Backend на FastAPI + PostgreSQL + Cloudflare R2
"""

import csv
import io
import os
import re
import secrets
import smtplib
import time
from collections import defaultdict
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
load_dotenv()
from datetime import timedelta, datetime
from pathlib import Path
from fastapi import FastAPI, File, UploadFile, HTTPException, Form, Depends, Header, BackgroundTasks, Request
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from typing import Optional
from fastapi.middleware.cors import CORSMiddleware
import bcrypt as _bcrypt
import psycopg2
from psycopg2.extras import DictCursor
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError


def verify_password(password: str, hashed: str) -> bool:
    return _bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))

def hash_password(password: str) -> str:
    return _bcrypt.hashpw(password.encode("utf-8"), _bcrypt.gensalt()).decode("utf-8")

# === Константы ===
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 МБ
ALLOWED_EXTENSIONS = {
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
    '.zip', '.rar', '.7z', '.png', '.jpg', '.jpeg', '.gif',
    '.txt', '.rtf', '.odt', '.ods', '.odp',
}

# === Настройка SMTP ===
SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_FROM = os.environ.get("SMTP_FROM") or SMTP_USER

def send_email(to: str, subject: str, body: str):
    if not all([SMTP_HOST, SMTP_USER, SMTP_PASSWORD, to]):
        return
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM
    msg["To"] = to
    msg.attach(MIMEText(body, "plain", "utf-8"))
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(SMTP_USER, SMTP_PASSWORD)
            smtp.sendmail(SMTP_FROM, to, msg.as_string())
    except Exception as e:
        print(f"[email] Ошибка отправки на {to}: {e}")
VALID_ID_PATTERN = re.compile(r"^[A-Za-z0-9\-_]+$")
SESSION_EXPIRE_HOURS = 24

# Rate limiting: не более 10 попыток входа с одного IP за 60 секунд
_login_attempts: dict = defaultdict(list)
_RATE_LIMIT_WINDOW = 60
_RATE_LIMIT_MAX = 10

def check_rate_limit(request: Request):
    ip = request.headers.get("X-Forwarded-For", "")
    ip = ip.split(",")[0].strip() if ip else (request.client.host if request.client else "unknown")
    now = time.time()
    _login_attempts[ip] = [t for t in _login_attempts[ip] if now - t < _RATE_LIMIT_WINDOW]
    if len(_login_attempts[ip]) >= _RATE_LIMIT_MAX:
        raise HTTPException(429, "Слишком много попыток входа. Попробуйте через минуту.")
    _login_attempts[ip].append(now)

# === Настройка БД ===
DATABASE_URL = os.environ.get("DATABASE_URL", "")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# === Настройка Cloudflare R2 ===
R2_BUCKET = os.environ.get("R2_BUCKET", "")
_r2_client = None


def get_r2():
    global _r2_client
    if _r2_client is None:
        endpoint = os.environ.get("R2_ENDPOINT_URL")
        key_id = os.environ.get("R2_ACCESS_KEY_ID")
        secret = os.environ.get("R2_SECRET_ACCESS_KEY")
        if not all([endpoint, key_id, secret, R2_BUCKET]):
            raise RuntimeError(
                "R2 не настроен: укажите R2_ENDPOINT_URL, R2_ACCESS_KEY_ID, "
                "R2_SECRET_ACCESS_KEY, R2_BUCKET"
            )
        _r2_client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=key_id,
            aws_secret_access_key=secret,
            config=Config(signature_version="s3v4"),
            region_name="auto",
        )
    return _r2_client


class DBConnection:
    """Обёртка над psycopg2: интерфейс conn.execute(...) → cursor с fetch* и dict-доступом."""

    def __init__(self, conn):
        self._conn = conn

    def execute(self, query, params=None):
        cur = self._conn.cursor(cursor_factory=DictCursor)
        if params is None:
            cur.execute(query)
        else:
            cur.execute(query, params)
        return cur

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if exc_type is None:
                self._conn.commit()
            else:
                self._conn.rollback()
        finally:
            self._conn.close()
        return False


def get_db():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL не задан в переменных окружения")
    conn = psycopg2.connect(DATABASE_URL)
    return DBConnection(conn)

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

# === Вспомогательные функции ===
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
    expires_at = datetime.now() + timedelta(hours=SESSION_EXPIRE_HOURS)

    with get_db() as conn:
        conn.execute("DELETE FROM sessions WHERE user_id = %s AND user_type = %s", (user_id, user_type))
        conn.execute("""
            INSERT INTO sessions (token, user_id, user_type, expires_at)
            VALUES (%s, %s, %s, %s)
        """, (token, user_id, user_type, expires_at))
    return token

def verify_session(token: str):
    if not token:
        return None

    current_time = datetime.now()
    with get_db() as conn:
        cur = conn.execute("SELECT user_id, user_type, expires_at FROM sessions WHERE token = %s", (token,))
        row = cur.fetchone()
        if not row:
            return None

        user_id, user_type, expires_at = row
        if expires_at <= current_time:
            conn.execute("DELETE FROM sessions WHERE token = %s", (token,))
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

def _r2_stream(r2_key: str, filename: str) -> StreamingResponse:
    """Стримит файл из R2 клиенту."""
    try:
        obj = get_r2().get_object(Bucket=R2_BUCKET, Key=r2_key)
        return StreamingResponse(
            obj["Body"],
            media_type="application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code in ("NoSuchKey", "404"):
            raise HTTPException(404, "Файл не найден")
        raise HTTPException(500, "Ошибка хранилища")

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

@app.get("/", response_class=HTMLResponse)
@app.get("/student", response_class=HTMLResponse)
async def root():
    with open("static/index.html", encoding="utf-8") as f:
        return HTMLResponse(f.read())

@app.get("/teacher", response_class=HTMLResponse)
async def teacher_page():
    with open("static/teacher.html", encoding="utf-8") as f:
        return HTMLResponse(f.read())

@app.get("/sw.js")
async def service_worker():
    return FileResponse("static/sw.js", media_type="application/javascript")

@app.get("/api/badge")
async def get_badge(session = Depends(require_auth)):
    user_id, user_type = session
    with get_db() as conn:
        if user_type == "student":
            cur = conn.execute("""
                SELECT COUNT(*) FROM submissions
                WHERE student_id = %s AND status = 'rejected'
            """, (user_id,))
        elif user_type == "teacher":
            cur = conn.execute("""
                SELECT COUNT(*) FROM submissions s
                JOIN assignments a ON a.id = s.assignment_id
                JOIN subject_teachers st ON st.subject_id = a.subject_id
                WHERE st.teacher_id = %s AND s.status IN ('submitted', 'resubmitted')
            """, (user_id,))
        else:
            return {"count": 0}
        return {"count": cur.fetchone()[0]}

# ===== СТУДЕНТ =====

@app.post("/api/login")
async def login(request: Request, student_id: str = Form(...), password: str = Form(...)):
    check_rate_limit(request)
    clean_id = validate_id(student_id)

    with get_db() as conn:
        cur = conn.execute("""
            SELECT id, last_name, first_name, patronymic, password_hash
            FROM students
            WHERE student_id = %s
        """, (clean_id,))
        student = cur.fetchone()
        if not student or not verify_password(password, student["password_hash"]):
            raise HTTPException(401, "Неверный номер студенческого или пароль")

        token = create_session(student["id"], "student")
        user = {k: student[k] for k in ("id", "last_name", "first_name", "patronymic")}
        return {"token": token, "user": user}

@app.post("/api/submit/{assignment_id}")
async def submit_work(
    assignment_id: int,
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    session = Depends(require_auth)
):
    user_id, user_type = session
    if user_type != "student":
        raise HTTPException(403, "Доступ запрещён")

    if not files or all(f.filename == "" for f in files):
        raise HTTPException(400, "Не выбраны файлы")
    if len([f for f in files if f.filename]) > 10:
        raise HTTPException(400, "Максимум 10 файлов за одну отправку")

    with get_db() as conn:
        cur = conn.execute("""
            SELECT a.id, a.title, s.name AS subject
            FROM assignments a JOIN subjects s ON a.subject_id = s.id
            WHERE a.id = %s
        """, (assignment_id,))
        assignment_row = cur.fetchone()
        if not assignment_row:
            raise HTTPException(404, "Задание не найдено")

        cur = conn.execute("""
            SELECT 1 FROM grades g
            JOIN assignments a ON a.subject_id = g.subject_id
            WHERE a.id = %s AND g.student_id = %s
        """, (assignment_id, user_id))
        if cur.fetchone():
            raise HTTPException(409, "Оценка по предмету уже выставлена. Повторная сдача недоступна.")
        assignment_title = assignment_row["title"]
        subject_name = assignment_row["subject"]

        conn.execute("""
            INSERT INTO submissions (student_id, assignment_id, status)
            VALUES (%s, %s, 'submitted')
            ON CONFLICT (student_id, assignment_id) DO NOTHING
        """, (user_id, assignment_id))

        cur = conn.execute("""
            SELECT id, status FROM submissions
            WHERE student_id = %s AND assignment_id = %s
        """, (user_id, assignment_id))
        submission_row = cur.fetchone()
        submission_id = submission_row[0]
        current_status = submission_row[1]

        new_status = "resubmitted" if current_status == "rejected" else "submitted"

        conn.execute("""
            UPDATE submissions
            SET status = %s, submitted_at = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (new_status, submission_id))

        cur = conn.execute("""
            SELECT st.last_name, st.first_name
            FROM students st WHERE st.id = %s
        """, (user_id,))
        student_row = cur.fetchone()
        student_name = f"{student_row['last_name']} {student_row['first_name']}" if student_row else "Студент"

        cur = conn.execute("""
            SELECT t.email FROM teachers t
            JOIN subject_teachers st_link ON t.id = st_link.teacher_id
            JOIN assignments a ON a.subject_id = st_link.subject_id
            WHERE a.id = %s AND t.email IS NOT NULL
        """, (assignment_id,))
        teacher_emails = [row[0] for row in cur.fetchall()]

        r2 = get_r2()
        saved_count = 0
        for file in files:
            if not file.filename:
                continue
            ext = os.path.splitext(file.filename)[1].lower()
            if ext not in ALLOWED_EXTENSIONS:
                raise HTTPException(400, f"Тип файла «{ext}» не разрешён. Допустимые форматы: PDF, DOC, DOCX, XLS, XLSX, ZIP, PNG, JPG и др.")
            if file.size > MAX_FILE_SIZE:
                raise HTTPException(400, f"Файл {file.filename} слишком большой (макс. 10 МБ)")
            safe_name = sanitize_filename(file.filename)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            r2_key = f"submissions/{user_id}/{assignment_id}/{timestamp}_{safe_name}"
            r2.upload_fileobj(file.file, R2_BUCKET, r2_key)
            conn.execute("""
                INSERT INTO submission_files (submission_id, file_path)
                VALUES (%s, %s)
            """, (submission_id, r2_key))
            saved_count += 1

    action = "повторно отправил" if new_status == "resubmitted" else "отправил"
    email_subject = f"Новая работа на проверку — {assignment_title}"
    email_body = (
        f"Студент {student_name} {action} работу «{assignment_title}» по предмету «{subject_name}».\n\n"
        f"Войдите в кабинет преподавателя для проверки."
    )
    for email in teacher_emails:
        background_tasks.add_task(send_email, email, email_subject, email_body)

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
            WHERE ss.student_id = %s
            ORDER BY a.deadline
        """, (user_id,))
        assignments_raw = cur.fetchall()

        all_assignment_ids = [a["id"] for a in assignments_raw]

        cur = conn.execute("""
            SELECT id, assignment_id, status, submitted_at, review
            FROM submissions
            WHERE student_id = %s
        """, (user_id,))
        submission_map = {}
        for row in cur.fetchall():
            submission_map[row["assignment_id"]] = {
                "submission_id": row["id"],
                "status": row["status"],
                "submitted_at": row["submitted_at"],
                "review": row["review"]
            }

        for aid in all_assignment_ids:
            if aid not in submission_map:
                submission_map[aid] = {
                    "submission_id": None,
                    "status": None,
                    "submitted_at": None,
                    "review": None
                }

        cur = conn.execute("""
            SELECT s.id AS subject_id,
                   STRING_AGG(
                       t.last_name || ' ' || substring(t.first_name, 1, 1) || '.' ||
                       CASE WHEN t.patronymic IS NOT NULL
                           THEN substring(t.patronymic, 1, 1) || '.'
                           ELSE '' END,
                       ', '
                   ) AS teachers
            FROM subjects s
            JOIN subject_teachers st_link ON s.id = st_link.subject_id
            JOIN teachers t ON st_link.teacher_id = t.id
            GROUP BY s.id
        """)
        teacher_map = {row["subject_id"]: row["teachers"] or "—" for row in cur.fetchall()}

        submission_ids = [v["submission_id"] for v in submission_map.values() if v["submission_id"]]
        has_feedback = set()
        if submission_ids:
            placeholders = ','.join(['%s'] * len(submission_ids))
            cur = conn.execute(f"""
                SELECT submission_id FROM teacher_feedback_files
                WHERE submission_id IN ({placeholders})
            """, submission_ids)
            has_feedback = {row[0] for row in cur.fetchall()}

        cur = conn.execute("""
            SELECT subject_id, status
            FROM grades
            WHERE student_id = %s
        """, (user_id,))
        grade_map = {row["subject_id"]: row["status"] for row in cur.fetchall()}

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
                "has_teacher_feedback": submission_map[a["id"]]["submission_id"] in has_feedback,
                "final_grade_blocked": a["subject_id"] in grade_map,
                "final_grade_status": grade_map.get(a["subject_id"])
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
            WHERE g.student_id = %s
            ORDER BY g.graded_at DESC
        """, (user_id,))

        grades = []
        for row in cur.fetchall():
            graded_at = row["graded_at"]
            formatted_date = "—"
            if graded_at:
                if isinstance(graded_at, datetime):
                    formatted_date = graded_at.strftime("%d.%m.%Y, %H:%M")
                else:
                    try:
                        formatted_date = datetime.fromisoformat(str(graded_at)).strftime("%d.%m.%Y, %H:%M")
                    except ValueError:
                        pass
            grades.append({
                "subject": row["subject"],
                "grade": row["grade"],
                "status": row["status"],
                "graded_at": formatted_date
            })
        return grades

# ===== ОБЩЕЕ =====

@app.post("/api/change-password")
async def change_password(
    old_password: str = Form(...),
    new_password: str = Form(...),
    session = Depends(require_auth)
):
    user_id, user_type = session
    if user_type == "admin":
        raise HTTPException(403, "Используйте /api/admin/change-password")
    if len(new_password) < 8:
        raise HTTPException(400, "Новый пароль должен содержать минимум 8 символов")

    table = "students" if user_type == "student" else "teachers"
    with get_db() as conn:
        cur = conn.execute(f"SELECT password_hash FROM {table} WHERE id = %s", (user_id,))
        row = cur.fetchone()
        if not row or not verify_password(old_password, row["password_hash"]):
            raise HTTPException(400, "Неверный текущий пароль")
        conn.execute(
            f"UPDATE {table} SET password_hash = %s WHERE id = %s",
            (hash_password(new_password), user_id)
        )
        conn.execute(
            "DELETE FROM sessions WHERE user_id = %s AND user_type = %s",
            (user_id, user_type)
        )
    return {"ok": True}


# ===== ПРЕПОДАВАТЕЛЬ =====

@app.post("/api/teacher/login")
async def teacher_login(request: Request, teacher_id: str = Form(...), password: str = Form(...)):
    check_rate_limit(request)
    clean_id = validate_id(teacher_id)

    with get_db() as conn:
        cur = conn.execute("""
            SELECT id, last_name, first_name, patronymic, password_hash
            FROM teachers
            WHERE teacher_id = %s
        """, (clean_id,))
        teacher = cur.fetchone()
        if not teacher or not verify_password(password, teacher["password_hash"]):
            raise HTTPException(401, "Неверный ID преподавателя или пароль")

        token = create_session(teacher["id"], "teacher")
        user = {k: teacher[k] for k in ("id", "last_name", "first_name", "patronymic")}
        return {"token": token, "user": user}

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
            WHERE st_link.teacher_id = %s
            AND (sub.status IS NULL OR sub.status NOT IN ('approved'))
            ORDER BY a.deadline DESC, st.last_name
        """, (user_id,))

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
            WHERE st_link.teacher_id = %s
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
            JOIN assignments a ON s.assignment_id = a.id
            JOIN subject_teachers sub_t ON a.subject_id = sub_t.subject_id
            WHERE s.assignment_id = %s AND st.student_id = %s AND sub_t.teacher_id = %s
        """, (assignment_id, clean_id, user_id))
        return [
            {
                "path": row[0],
                "name": os.path.basename(row[0])
            }
            for row in cur.fetchall()
        ]

@app.post("/api/teacher/grade")
async def set_grade(
    background_tasks: BackgroundTasks,
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
        cur = conn.execute("""
            SELECT id, last_name, first_name, email FROM students WHERE student_id = %s
        """, (clean_student_id,))
        student_row = cur.fetchone()
        if not student_row:
            raise HTTPException(404, "Студент не найден")
        student_id_int = student_row["id"]
        student_name = f"{student_row['last_name']} {student_row['first_name']}"
        student_email = student_row["email"]

        cur = conn.execute("SELECT id FROM subjects WHERE name = %s", (subject_name,))
        subject_row = cur.fetchone()
        if not subject_row:
            raise HTTPException(404, "Предмет не найден")
        subject_id_int = subject_row[0]

        cur = conn.execute("""
            SELECT 1 FROM subject_teachers
            WHERE subject_id = %s AND teacher_id = %s
        """, (subject_id_int, user_id))
        if not cur.fetchone():
            raise HTTPException(403, "Вы не ведёте этот предмет")

        cur = conn.execute("""
            SELECT 1 FROM assignments WHERE id = %s AND subject_id = %s
        """, (assignment_id, subject_id_int))
        if not cur.fetchone():
            raise HTTPException(403, "Задание не принадлежит этому предмету")

        cur = conn.execute("SELECT title FROM assignments WHERE id = %s", (assignment_id,))
        assignment_row = cur.fetchone()
        assignment_title = assignment_row["title"] if assignment_row else "Задание"

        if status_input == "не зачтено":
            cur = conn.execute("""
                SELECT id FROM submissions
                WHERE student_id = %s AND assignment_id = %s
            """, (student_id_int, assignment_id))
            submission_row = cur.fetchone()
            if submission_row:
                submission_id = submission_row[0]
                cur = conn.execute(
                    "SELECT file_path FROM submission_files WHERE submission_id = %s",
                    (submission_id,)
                )
                r2_keys = [row[0] for row in cur.fetchall()]
                if r2_keys:
                    try:
                        get_r2().delete_objects(
                            Bucket=R2_BUCKET,
                            Delete={"Objects": [{"Key": k} for k in r2_keys]},
                        )
                    except ClientError:
                        pass
                conn.execute("DELETE FROM submission_files WHERE submission_id = %s", (submission_id,))

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
            SET status = %s, review = %s
            WHERE student_id = %s AND assignment_id = %s
        """, (db_status, review, student_id_int, assignment_id))

        grade_value = 100 if status_input in ("зачёт", "сдано") else None
        conn.execute("""
            INSERT INTO grades (student_id, subject_id, grade, status, review, graded_at)
            VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (student_id, subject_id)
            DO UPDATE SET
                grade = EXCLUDED.grade,
                status = EXCLUDED.status,
                review = EXCLUDED.review,
                graded_at = EXCLUDED.graded_at
        """, (student_id_int, subject_id_int, grade_value, status_input, review))

    if student_email:
        STATUS_LABELS = {
            "зачёт": "Зачтено",
            "сдано": "Зачтено",
            "не зачтено": "Не зачтено — требуется повторная сдача",
            "не допущен": "Не допущен",
            "не сдано": "Не зачтено",
            "принят на рассмотрение": "Принято на рассмотрение",
        }
        status_label = STATUS_LABELS.get(status_input, status_input)
        review_line = f"Рецензия: {review}" if review else ""
        email_body = (
            f"Здравствуйте, {student_name}!\n\n"
            f"Преподаватель проверил вашу работу «{assignment_title}» по предмету «{subject_name}».\n\n"
            f"Статус: {status_label}\n"
            f"{review_line}\n\n"
            f"Войдите в личный кабинет для подробностей."
        ).strip()
        background_tasks.add_task(
            send_email,
            student_email,
            f"Статус работы изменён — {assignment_title}",
            email_body,
        )

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
        raise HTTPException(400, "Файл слишком большой (макс. 10 МБ)")

    with get_db() as conn:
        cur = conn.execute("""
            SELECT s.id
            FROM submissions s
            JOIN assignments a ON s.assignment_id = a.id
            JOIN subjects subj ON a.subject_id = subj.id
            JOIN subject_teachers st ON subj.id = st.subject_id
            JOIN students stud ON s.student_id = stud.id
            WHERE s.assignment_id = %s AND stud.student_id = %s AND st.teacher_id = %s
        """, (assignment_id, clean_student_id, user_id))
        submission_row = cur.fetchone()
        if not submission_row:
            raise HTTPException(403, "Нет доступа к этой работе")

        submission_id = submission_row[0]

        safe_name = sanitize_filename(file.filename)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        r2_key = f"feedback/{clean_student_id}/{assignment_id}/{timestamp}_{safe_name}"

        get_r2().upload_fileobj(file.file, R2_BUCKET, r2_key)

        conn.execute("""
            INSERT INTO teacher_feedback_files (submission_id, file_path)
            VALUES (%s, %s)
        """, (submission_id, r2_key))

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
            WHERE tf.submission_id = %s
        """, (submission_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Файл не найден")

        r2_key, student_id = row
        if student_id != user_id:
            raise HTTPException(403, "Нет доступа к этому файлу")

    return _r2_stream(r2_key, os.path.basename(r2_key))

# ===== АДМИНИСТРАТОР =====

@app.get("/admin", response_class=HTMLResponse)
async def admin_page():
    with open("static/admin.html", encoding="utf-8") as f:
        return HTMLResponse(f.read())

async def require_admin(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Требуется авторизация")
    token = authorization.split(" ", 1)[1]
    session = verify_session(token)
    if not session:
        raise HTTPException(401, "Неверный или просроченный токен")
    user_id, user_type = session
    if user_type != "admin":
        raise HTTPException(403, "Доступ запрещён")
    return user_id

@app.post("/api/admin/login")
async def admin_login(request: Request, admin_id: str = Form(...), password: str = Form(...)):
    check_rate_limit(request)
    clean_id = validate_id(admin_id)
    with get_db() as conn:
        cur = conn.execute("SELECT id, password_hash FROM admins WHERE admin_id = %s", (clean_id,))
        admin = cur.fetchone()
        if not admin or not verify_password(password, admin["password_hash"]):
            raise HTTPException(401, "Неверный логин или пароль")
        token = create_session(admin["id"], "admin")
        return {"token": token}

@app.post("/api/admin/change-password")
async def admin_change_password(
    old_password: str = Form(...),
    new_password: str = Form(...),
    admin_id = Depends(require_admin)
):
    if len(new_password) < 8:
        raise HTTPException(400, "Новый пароль должен содержать минимум 8 символов")
    with get_db() as conn:
        cur = conn.execute("SELECT password_hash FROM admins WHERE id = %s", (admin_id,))
        row = cur.fetchone()
        if not row or not verify_password(old_password, row["password_hash"]):
            raise HTTPException(400, "Неверный текущий пароль")
        conn.execute("UPDATE admins SET password_hash = %s WHERE id = %s", (hash_password(new_password), admin_id))
    return {"ok": True}

# --- Студенты ---

@app.get("/api/admin/stats")
async def admin_stats(admin_id = Depends(require_admin)):
    with get_db() as conn:
        students = conn.execute("SELECT COUNT(*) FROM students").fetchone()[0]
        teachers = conn.execute("SELECT COUNT(*) FROM teachers").fetchone()[0]
        pending = conn.execute("""
            SELECT COUNT(*) FROM submissions
            WHERE status IN ('submitted', 'in_review', 'resubmitted')
        """).fetchone()[0]
        overdue = conn.execute("""
            SELECT COUNT(*) FROM (
                SELECT ss.student_id, a.id
                FROM student_subjects ss
                JOIN assignments a ON a.subject_id = ss.subject_id
                WHERE a.deadline < CURRENT_DATE
                AND NOT EXISTS (
                    SELECT 1 FROM submissions sub
                    WHERE sub.student_id = ss.student_id
                    AND sub.assignment_id = a.id
                    AND sub.status = 'approved'
                )
            ) t
        """).fetchone()[0]
    return {"students": students, "teachers": teachers, "pending": pending, "overdue": overdue}

@app.get("/api/admin/export/students")
async def admin_export_students(admin_id = Depends(require_admin)):
    with get_db() as conn:
        rows = conn.execute("""
            SELECT student_id, last_name, first_name, patronymic, group_name, email
            FROM students ORDER BY group_name, last_name, first_name
        """).fetchall()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["ID", "Фамилия", "Имя", "Отчество", "Группа", "Email"])
    for r in rows:
        w.writerow([r[0], r[1], r[2], r[3] or "", r[4] or "", r[5] or ""])
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue().encode("utf-8-sig")]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=students.csv"})

@app.get("/api/admin/export/grades")
async def admin_export_grades(admin_id = Depends(require_admin)):
    with get_db() as conn:
        rows = conn.execute("""
            SELECT st.student_id, st.last_name, st.first_name, st.group_name,
                   subj.name AS subject, a.title, a.deadline,
                   COALESCE(sub.status, 'не сдано') AS status,
                   sub.submitted_at
            FROM student_subjects ss
            JOIN students st ON st.id = ss.student_id
            JOIN subjects subj ON subj.id = ss.subject_id
            JOIN assignments a ON a.subject_id = ss.subject_id
            LEFT JOIN submissions sub ON sub.student_id = ss.student_id AND sub.assignment_id = a.id
            ORDER BY st.group_name, st.last_name, subj.name, a.title
        """).fetchall()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["ID студента", "Фамилия", "Имя", "Группа", "Предмет", "Задание", "Дедлайн", "Статус", "Дата сдачи"])
    for r in rows:
        deadline = r[6].strftime("%d.%m.%Y") if r[6] else ""
        submitted = r[8].strftime("%d.%m.%Y %H:%M") if r[8] else ""
        w.writerow([r[0], r[1], r[2], r[3] or "", r[4], r[5], deadline, r[7], submitted])
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue().encode("utf-8-sig")]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=grades.csv"})

@app.get("/api/admin/students")
async def admin_list_students(admin_id = Depends(require_admin)):
    with get_db() as conn:
        cur = conn.execute("""
            SELECT id, student_id, last_name, first_name, patronymic, group_name, email
            FROM students ORDER BY last_name, first_name
        """)
        return [dict(r) for r in cur.fetchall()]

@app.post("/api/admin/students")
async def admin_add_student(
    student_id: str = Form(...),
    last_name: str = Form(...),
    first_name: str = Form(...),
    patronymic: str = Form(None),
    group_name: str = Form(None),
    email: str = Form(None),
    admin_id = Depends(require_admin)
):
    clean_id = validate_id(student_id)
    temp_password = secrets.token_hex(4)
    with get_db() as conn:
        try:
            conn.execute("""
                INSERT INTO students (student_id, last_name, first_name, patronymic, group_name, email, password_hash)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (clean_id, last_name, first_name, patronymic or None, group_name or None,
                  email or None, hash_password(temp_password)))
        except Exception:
            raise HTTPException(400, "Студент с таким ID уже существует")
    return {"ok": True, "temp_password": temp_password}

@app.put("/api/admin/students/{student_db_id}")
async def admin_edit_student(
    student_db_id: int,
    last_name: str = Form(...),
    first_name: str = Form(...),
    patronymic: str = Form(None),
    group_name: str = Form(None),
    email: str = Form(None),
    admin_id = Depends(require_admin)
):
    with get_db() as conn:
        cur = conn.execute("SELECT id FROM students WHERE id = %s", (student_db_id,))
        if not cur.fetchone():
            raise HTTPException(404, "Студент не найден")
        conn.execute("""
            UPDATE students SET last_name=%s, first_name=%s, patronymic=%s, group_name=%s, email=%s
            WHERE id=%s
        """, (last_name, first_name, patronymic or None, group_name or None, email or None, student_db_id))
    return {"ok": True}

@app.post("/api/admin/students/{student_db_id}/reset-password")
async def admin_reset_student_password(student_db_id: int, admin_id = Depends(require_admin)):
    with get_db() as conn:
        cur = conn.execute("SELECT id FROM students WHERE id = %s", (student_db_id,))
        if not cur.fetchone():
            raise HTTPException(404, "Студент не найден")
        temp_password = secrets.token_hex(4)
        conn.execute("UPDATE students SET password_hash = %s WHERE id = %s",
                     (hash_password(temp_password), student_db_id))
    return {"ok": True, "temp_password": temp_password}

@app.delete("/api/admin/students/{student_db_id}")
async def admin_delete_student(student_db_id: int, admin_id = Depends(require_admin)):
    with get_db() as conn:
        cur = conn.execute("SELECT id FROM students WHERE id = %s", (student_db_id,))
        if not cur.fetchone():
            raise HTTPException(404, "Студент не найден")
        conn.execute("DELETE FROM students WHERE id = %s", (student_db_id,))
    return {"ok": True}

# --- Преподаватели ---

@app.get("/api/admin/teachers")
async def admin_list_teachers(admin_id = Depends(require_admin)):
    with get_db() as conn:
        cur = conn.execute("""
            SELECT id, teacher_id, last_name, first_name, patronymic, email
            FROM teachers ORDER BY last_name, first_name
        """)
        return [dict(r) for r in cur.fetchall()]

@app.post("/api/admin/teachers")
async def admin_add_teacher(
    teacher_id: str = Form(...),
    last_name: str = Form(...),
    first_name: str = Form(...),
    patronymic: str = Form(None),
    email: str = Form(None),
    admin_id = Depends(require_admin)
):
    clean_id = validate_id(teacher_id)
    temp_password = secrets.token_hex(4)
    with get_db() as conn:
        try:
            conn.execute("""
                INSERT INTO teachers (teacher_id, last_name, first_name, patronymic, email, password_hash)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (clean_id, last_name, first_name, patronymic or None,
                  email or None, hash_password(temp_password)))
        except Exception:
            raise HTTPException(400, "Преподаватель с таким ID уже существует")
    return {"ok": True, "temp_password": temp_password}

@app.put("/api/admin/teachers/{teacher_db_id}")
async def admin_edit_teacher(
    teacher_db_id: int,
    last_name: str = Form(...),
    first_name: str = Form(...),
    patronymic: str = Form(None),
    email: str = Form(None),
    admin_id = Depends(require_admin)
):
    with get_db() as conn:
        cur = conn.execute("SELECT id FROM teachers WHERE id = %s", (teacher_db_id,))
        if not cur.fetchone():
            raise HTTPException(404, "Преподаватель не найден")
        conn.execute("""
            UPDATE teachers SET last_name=%s, first_name=%s, patronymic=%s, email=%s
            WHERE id=%s
        """, (last_name, first_name, patronymic or None, email or None, teacher_db_id))
    return {"ok": True}

@app.post("/api/admin/teachers/{teacher_db_id}/reset-password")
async def admin_reset_teacher_password(teacher_db_id: int, admin_id = Depends(require_admin)):
    with get_db() as conn:
        cur = conn.execute("SELECT id FROM teachers WHERE id = %s", (teacher_db_id,))
        if not cur.fetchone():
            raise HTTPException(404, "Преподаватель не найден")
        temp_password = secrets.token_hex(4)
        conn.execute("UPDATE teachers SET password_hash = %s WHERE id = %s",
                     (hash_password(temp_password), teacher_db_id))
    return {"ok": True, "temp_password": temp_password}

@app.delete("/api/admin/teachers/{teacher_db_id}")
async def admin_delete_teacher(teacher_db_id: int, admin_id = Depends(require_admin)):
    with get_db() as conn:
        cur = conn.execute("SELECT id FROM teachers WHERE id = %s", (teacher_db_id,))
        if not cur.fetchone():
            raise HTTPException(404, "Преподаватель не найден")
        conn.execute("DELETE FROM teachers WHERE id = %s", (teacher_db_id,))
    return {"ok": True}

# --- Предметы ---

@app.get("/api/admin/subjects")
async def admin_list_subjects(admin_id = Depends(require_admin)):
    with get_db() as conn:
        cur = conn.execute("""
            SELECT s.id, s.name, s.code, s.semester,
                   COALESCE(STRING_AGG(t.last_name || ' ' || t.first_name, ', '), '') AS teachers
            FROM subjects s
            LEFT JOIN subject_teachers st ON st.subject_id = s.id
            LEFT JOIN teachers t ON t.id = st.teacher_id
            GROUP BY s.id ORDER BY s.name
        """)
        return [dict(r) for r in cur.fetchall()]

@app.post("/api/admin/subjects")
async def admin_add_subject(
    name: str = Form(...),
    code: str = Form(None),
    semester: str = Form(None),
    admin_id = Depends(require_admin)
):
    with get_db() as conn:
        try:
            cur = conn.execute("""
                INSERT INTO subjects (name, code, semester) VALUES (%s, %s, %s) RETURNING id
            """, (name, code or None, semester or None))
            return {"ok": True, "id": cur.fetchone()[0]}
        except Exception:
            raise HTTPException(400, "Предмет с таким названием уже существует")

@app.delete("/api/admin/subjects/{subject_id}")
async def admin_delete_subject(subject_id: int, admin_id = Depends(require_admin)):
    with get_db() as conn:
        cur = conn.execute("SELECT id FROM subjects WHERE id = %s", (subject_id,))
        if not cur.fetchone():
            raise HTTPException(404, "Предмет не найден")
        conn.execute("DELETE FROM subjects WHERE id = %s", (subject_id,))
    return {"ok": True}

@app.post("/api/admin/subjects/{subject_id}/teachers")
async def admin_assign_teacher(
    subject_id: int,
    teacher_id: int = Form(...),
    admin_id = Depends(require_admin)
):
    with get_db() as conn:
        conn.execute("""
            INSERT INTO subject_teachers (subject_id, teacher_id) VALUES (%s, %s)
            ON CONFLICT DO NOTHING
        """, (subject_id, teacher_id))
    return {"ok": True}

@app.delete("/api/admin/subjects/{subject_id}/teachers/{teacher_id}")
async def admin_remove_teacher(subject_id: int, teacher_id: int, admin_id = Depends(require_admin)):
    with get_db() as conn:
        conn.execute("DELETE FROM subject_teachers WHERE subject_id = %s AND teacher_id = %s",
                     (subject_id, teacher_id))
    return {"ok": True}

@app.post("/api/admin/subjects/{subject_id}/students")
async def admin_enroll_student(
    subject_id: int,
    student_id: int = Form(...),
    admin_id = Depends(require_admin)
):
    with get_db() as conn:
        conn.execute("""
            INSERT INTO student_subjects (student_id, subject_id) VALUES (%s, %s)
            ON CONFLICT DO NOTHING
        """, (student_id, subject_id))
    return {"ok": True}

@app.post("/api/admin/subjects/{subject_id}/students/bulk")
async def admin_bulk_enroll_students(subject_id: int, request: Request, admin_id = Depends(require_admin)):
    body = await request.json()
    student_ids = body.get("student_ids", [])
    if not student_ids:
        raise HTTPException(400, "Список студентов пуст")
    with get_db() as conn:
        for sid in student_ids:
            conn.execute("""
                INSERT INTO student_subjects (student_id, subject_id) VALUES (%s, %s)
                ON CONFLICT DO NOTHING
            """, (sid, subject_id))
    return {"ok": True, "enrolled": len(student_ids)}

@app.delete("/api/admin/subjects/{subject_id}/students/{student_id}")
async def admin_unenroll_student(subject_id: int, student_id: int, admin_id = Depends(require_admin)):
    with get_db() as conn:
        conn.execute("DELETE FROM student_subjects WHERE student_id = %s AND subject_id = %s",
                     (student_id, subject_id))
    return {"ok": True}

@app.get("/api/admin/subjects/{subject_id}/members")
async def admin_subject_members(subject_id: int, admin_id = Depends(require_admin)):
    with get_db() as conn:
        t_cur = conn.execute("""
            SELECT t.id, t.teacher_id, t.last_name || ' ' || t.first_name AS name
            FROM subject_teachers st JOIN teachers t ON t.id = st.teacher_id
            WHERE st.subject_id = %s
        """, (subject_id,))
        s_cur = conn.execute("""
            SELECT s.id, s.student_id, s.last_name || ' ' || s.first_name AS name
            FROM student_subjects ss JOIN students s ON s.id = ss.student_id
            WHERE ss.subject_id = %s
        """, (subject_id,))
        return {"teachers": [dict(r) for r in t_cur.fetchall()],
                "students": [dict(r) for r in s_cur.fetchall()]}

# --- Задания ---

@app.get("/api/admin/assignments")
async def admin_list_assignments(admin_id = Depends(require_admin)):
    with get_db() as conn:
        cur = conn.execute("""
            SELECT a.id, a.subject_id, a.title, a.description, a.deadline, s.name AS subject
            FROM assignments a JOIN subjects s ON s.id = a.subject_id
            ORDER BY a.deadline DESC NULLS LAST
        """)
        rows = []
        for r in cur.fetchall():
            d = dict(r)
            d["deadline"] = d["deadline"].strftime("%Y-%m-%d") if d["deadline"] else None
            rows.append(d)
        return rows

@app.post("/api/admin/assignments")
async def admin_add_assignment(
    subject_id: int = Form(...),
    title: str = Form(...),
    description: str = Form(None),
    deadline: str = Form(None),
    admin_id = Depends(require_admin)
):
    with get_db() as conn:
        cur = conn.execute("""
            INSERT INTO assignments (subject_id, title, description, deadline) VALUES (%s, %s, %s, %s) RETURNING id
        """, (subject_id, title, description or None, deadline or None))
        return {"ok": True, "id": cur.fetchone()[0]}

@app.put("/api/admin/assignments/{assignment_id}")
async def admin_edit_assignment(
    assignment_id: int,
    subject_id: int = Form(...),
    title: str = Form(...),
    description: str = Form(None),
    deadline: str = Form(None),
    admin_id = Depends(require_admin)
):
    with get_db() as conn:
        cur = conn.execute("SELECT id FROM assignments WHERE id = %s", (assignment_id,))
        if not cur.fetchone():
            raise HTTPException(404, "Задание не найдено")
        conn.execute("""
            UPDATE assignments SET subject_id=%s, title=%s, description=%s, deadline=%s WHERE id=%s
        """, (subject_id, title, description or None, deadline or None, assignment_id))
    return {"ok": True}

@app.delete("/api/admin/assignments/{assignment_id}")
async def admin_delete_assignment(assignment_id: int, admin_id = Depends(require_admin)):
    with get_db() as conn:
        cur = conn.execute("SELECT id FROM assignments WHERE id = %s", (assignment_id,))
        if not cur.fetchone():
            raise HTTPException(404, "Задание не найдено")
        conn.execute("DELETE FROM assignments WHERE id = %s", (assignment_id,))
    return {"ok": True}


# ===== ПРОГРЕСС СТУДЕНТОВ =====

@app.get("/api/teacher/progress")
async def get_teacher_progress(subject_id: Optional[int] = None, session = Depends(require_auth)):
    user_id, user_type = session
    if user_type != "teacher":
        raise HTTPException(403, "Доступ запрещён")

    with get_db() as conn:
        cur = conn.execute("""
            SELECT DISTINCT subj.id, subj.name
            FROM subjects subj
            JOIN subject_teachers st_link ON subj.id = st_link.subject_id
            WHERE st_link.teacher_id = %s
            ORDER BY subj.name
        """, (user_id,))
        subjects = [dict(r) for r in cur.fetchall()]

        query = """
            SELECT
                st.last_name || ' ' || st.first_name AS student_name,
                st.student_id,
                subj.id AS subject_id,
                subj.name AS subject,
                a.id AS assignment_id,
                a.title AS assignment_title,
                a.deadline,
                sub.status,
                sub.submitted_at
            FROM assignments a
            JOIN subjects subj ON a.subject_id = subj.id
            JOIN subject_teachers st_link ON subj.id = st_link.subject_id
            JOIN student_subjects ss ON subj.id = ss.subject_id
            JOIN students st ON ss.student_id = st.id
            LEFT JOIN submissions sub ON sub.assignment_id = a.id AND sub.student_id = st.id
            WHERE st_link.teacher_id = %s
        """
        params = [user_id]
        if subject_id:
            query += " AND subj.id = %s"
            params.append(subject_id)
        query += " ORDER BY subj.name, st.last_name, a.deadline"

        cur = conn.execute(query, params)
        rows = []
        for r in cur.fetchall():
            d = dict(r)
            d["deadline"] = d["deadline"].isoformat() if d["deadline"] else None
            d["submitted_at"] = d["submitted_at"].isoformat() if d["submitted_at"] else None
            rows.append(d)

        return {"subjects": subjects, "rows": rows}


# ===== СКАЧИВАНИЕ ФАЙЛОВ =====

@app.get("/download/{path:path}")
async def download_file(path: str, session = Depends(require_auth)):
    if ".." in path or path.startswith("/"):
        raise HTTPException(400, "Некорректный путь")

    user_id, user_type = session

    if user_type != "admin":
        with get_db() as conn:
            if user_type == "student":
                cur = conn.execute("""
                    SELECT 1 FROM submission_files sf
                    JOIN submissions sub ON sf.submission_id = sub.id
                    WHERE sf.file_path = %s AND sub.student_id = %s
                    UNION ALL
                    SELECT 1 FROM teacher_feedback_files tff
                    JOIN submissions sub ON tff.submission_id = sub.id
                    WHERE tff.file_path = %s AND sub.student_id = %s
                """, (path, user_id, path, user_id))
            else:  # teacher
                cur = conn.execute("""
                    SELECT 1 FROM submission_files sf
                    JOIN submissions sub ON sf.submission_id = sub.id
                    JOIN assignments a ON sub.assignment_id = a.id
                    JOIN subject_teachers st ON a.subject_id = st.subject_id
                    WHERE sf.file_path = %s AND st.teacher_id = %s
                    UNION ALL
                    SELECT 1 FROM teacher_feedback_files tff
                    JOIN submissions sub ON tff.submission_id = sub.id
                    JOIN assignments a ON sub.assignment_id = a.id
                    JOIN subject_teachers st ON a.subject_id = st.subject_id
                    WHERE tff.file_path = %s AND st.teacher_id = %s
                """, (path, user_id, path, user_id))
            if not cur.fetchone():
                raise HTTPException(403, "Доступ запрещён")

    return _r2_stream(path, os.path.basename(path))
