"""
Эндпоинты студента: сдача работ, список заданий, оценки, файлы обратной связи.
"""

import os
from datetime import datetime

from fastapi import APIRouter, File, UploadFile, HTTPException, Depends, BackgroundTasks

from db import get_db
from auth import require_auth
from storage import get_r2, R2_BUCKET, r2_stream
from email_service import send_email
from utils import sanitize_filename
from constants import MAX_FILE_SIZE, ALLOWED_EXTENSIONS, STATUS_LABELS, STATUS_LABELS_GRADES

router = APIRouter()


@router.post("/api/submit/{assignment_id}")
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
            if (file.size or 0) > MAX_FILE_SIZE:
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


@router.post("/api/submit-notebook/{assignment_id}")
async def submit_notebook(
    assignment_id: int,
    background_tasks: BackgroundTasks,
    session = Depends(require_auth)
):
    user_id, user_type = session
    if user_type != "student":
        raise HTTPException(403, "Доступ запрещён")

    with get_db() as conn:
        cur = conn.execute("""
            SELECT a.id, a.title, a.submission_type, s.name AS subject
            FROM assignments a JOIN subjects s ON a.subject_id = s.id
            WHERE a.id = %s
        """, (assignment_id,))
        assignment_row = cur.fetchone()
        if not assignment_row:
            raise HTTPException(404, "Задание не найдено")
        if assignment_row["submission_type"] != "notebook":
            raise HTTPException(400, "Это задание сдаётся в электронном виде")

        cur = conn.execute("""
            SELECT id, status FROM submissions
            WHERE student_id = %s AND assignment_id = %s
        """, (user_id, assignment_id))
        existing = cur.fetchone()

        if existing and existing["status"] == "approved":
            raise HTTPException(409, "Работа уже зачтена.")

        conn.execute("""
            INSERT INTO submissions (student_id, assignment_id, status, submitted_at)
            VALUES (%s, %s, 'notebook_sent', CURRENT_TIMESTAMP)
            ON CONFLICT (student_id, assignment_id)
            DO UPDATE SET status = 'notebook_sent', submitted_at = CURRENT_TIMESTAMP
        """, (user_id, assignment_id))

        cur = conn.execute("""
            SELECT last_name, first_name FROM students WHERE id = %s
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

    assignment_title = assignment_row["title"]
    subject_name = assignment_row["subject"]
    for email in teacher_emails:
        background_tasks.add_task(
            send_email, email,
            f"Тетрадь отправлена почтой — {assignment_title}",
            f"Студент {student_name} отметил отправку тетради по заданию «{assignment_title}» "
            f"(предмет «{subject_name}») почтой.\n\nВойдите в кабинет преподавателя для проверки."
        )

    return {"message": "Отмечено как отправлено почтой"}


@router.get("/api/assignments/me")
async def get_my_assignments(session = Depends(require_auth)):
    user_id, user_type = session
    if user_type != "student":
        raise HTTPException(403, "Доступ запрещён")

    with get_db() as conn:
        cur = conn.execute("""
            SELECT a.id, a.title, a.description, a.deadline, a.submission_type,
                   s.id AS subject_id, s.name AS subject
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
        feedback_files_map: dict = {}
        if submission_ids:
            placeholders = ','.join(['%s'] * len(submission_ids))
            cur = conn.execute(f"""
                SELECT id, submission_id, file_path FROM teacher_feedback_files
                WHERE submission_id IN ({placeholders})
                ORDER BY uploaded_at
            """, submission_ids)
            for row in cur.fetchall():
                feedback_files_map.setdefault(row["submission_id"], []).append(
                    {"id": row["id"], "name": os.path.basename(row["file_path"])}
                )

        cur = conn.execute("""
            SELECT subject_id, status
            FROM grades
            WHERE student_id = %s
        """, (user_id,))
        grade_map = {row["subject_id"]: row["status"] for row in cur.fetchall()}

        return [
            {
                "id": a["id"],
                "subject": a["subject"],
                "teachers": teacher_map.get(a["subject_id"], "—"),
                "title": a["title"],
                "description": a["description"],
                "deadline": a["deadline"],
                "submission_type": a["submission_type"] or "electronic",
                "status": submission_map[a["id"]]["status"],
                "status_label": STATUS_LABELS.get(submission_map[a["id"]]["status"], "Не отправлено"),
                "submitted_at": submission_map[a["id"]]["submitted_at"],
                "review": submission_map[a["id"]]["review"],
                "submission_id": submission_map[a["id"]]["submission_id"],
                "feedback_files": feedback_files_map.get(submission_map[a["id"]]["submission_id"], []),
                "final_grade_blocked": a["subject_id"] in grade_map,
                "final_grade_status": grade_map.get(a["subject_id"])
            }
            for a in assignments_raw
        ]


@router.get("/api/grades/me")
async def get_my_grades(session = Depends(require_auth)):
    user_id, user_type = session
    if user_type != "student":
        raise HTTPException(403, "Доступ запрещён")

    with get_db() as conn:
        cur = conn.execute("""
            SELECT s.name AS subject, a.title AS assignment_title,
                   sub.status, sub.submitted_at
            FROM submissions sub
            JOIN assignments a ON sub.assignment_id = a.id
            JOIN subjects s ON a.subject_id = s.id
            WHERE sub.student_id = %s
            ORDER BY sub.submitted_at DESC NULLS LAST
        """, (user_id,))

        result = []
        for row in cur.fetchall():
            ts = row["submitted_at"]
            formatted_date = "—"
            if ts:
                if isinstance(ts, datetime):
                    formatted_date = ts.strftime("%d.%m.%Y, %H:%M")
                else:
                    try:
                        formatted_date = datetime.fromisoformat(str(ts)).strftime("%d.%m.%Y, %H:%M")
                    except ValueError:
                        pass
            result.append({
                "subject":          row["subject"],
                "assignment_title": row["assignment_title"],
                "status":           row["status"],
                "status_label":     STATUS_LABELS_GRADES.get(row["status"], row["status"] or "—"),
                "submitted_at":     formatted_date,
            })
        return result


@router.get("/api/download/feedback-file/{file_id}")
async def download_feedback_file_by_id(file_id: int, session = Depends(require_auth)):
    user_id, user_type = session
    if user_type != "student":
        raise HTTPException(403, "Доступ запрещён")

    with get_db() as conn:
        cur = conn.execute("""
            SELECT tf.file_path
            FROM teacher_feedback_files tf
            JOIN submissions s ON tf.submission_id = s.id
            WHERE tf.id = %s AND s.student_id = %s
        """, (file_id, user_id))
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Файл не найден")

    return r2_stream(row[0], os.path.basename(row[0]))
