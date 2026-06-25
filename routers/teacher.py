"""
Эндпоинты преподавателя: задания на проверку, статистика, история,
файлы работ, выставление статуса/оценки, файлы обратной связи, прогресс.
"""

import os
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, File, UploadFile, HTTPException, Form, Depends, BackgroundTasks
from botocore.exceptions import ClientError

from db import get_db
from auth import require_auth, validate_id
from storage import get_r2, R2_BUCKET
from email_service import send_email
from utils import sanitize_filename
from constants import MAX_FILE_SIZE, ALLOWED_EXTENSIONS, STATUS_LABELS

router = APIRouter()


@router.get("/api/teacher/assignments/me")
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
                a.submission_type,
                s.name AS subject,
                st.last_name || ' ' || st.first_name AS student_name,
                st.id AS student_db_id,
                st.student_id,
                sub.submitted_at,
                sub.status AS last_status,
                g.graded_at AS last_action_at
            FROM assignments a
            JOIN subjects s ON a.subject_id = s.id
            JOIN subject_teachers st_link ON s.id = st_link.subject_id
            JOIN student_subjects ss ON ss.subject_id = s.id
            JOIN students st ON ss.student_id = st.id
            LEFT JOIN submissions sub ON sub.assignment_id = a.id AND sub.student_id = st.id
            LEFT JOIN grades g ON g.student_id = st.id AND g.subject_id = s.id
            WHERE st_link.teacher_id = %s
            AND (
                (COALESCE(a.submission_type, 'electronic') = 'electronic'
                 AND sub.id IS NOT NULL
                 AND (sub.status IS NULL OR sub.status NOT IN ('approved')))
                OR
                (a.submission_type = 'notebook'
                 AND (sub.status IS NULL OR sub.status NOT IN ('approved')))
            )
            ORDER BY a.deadline DESC, st.last_name
        """, (user_id,))

        result = []
        for row in cur.fetchall():
            stype = row["submission_type"] or "electronic"
            last_status = row["last_status"]
            if last_status is None and stype == "notebook":
                status_label = "Нет в кабинете"
            else:
                status_label = STATUS_LABELS.get(last_status, "Не отмечено")
            result.append({
                "assignment_id": row["assignment_id"],
                "title": row["title"],
                "deadline": row["deadline"],
                "submission_type": stype,
                "subject": row["subject"],
                "student_name": row["student_name"],
                "student_db_id": row["student_db_id"],
                "student_id": row["student_id"],
                "submitted_at": row["submitted_at"],
                "last_status": last_status,
                "last_status_label": status_label,
                "last_action_at": row["last_action_at"]
            })
        return result


@router.get("/api/teacher/stats/me")
async def get_teacher_stats(session = Depends(require_auth)):
    user_id, user_type = session
    if user_type != "teacher":
        raise HTTPException(403, "Доступ запрещён")
    with get_db() as conn:
        pending = conn.execute("""
            SELECT COUNT(*) FROM submissions sub
            JOIN assignments a ON sub.assignment_id = a.id
            JOIN subject_teachers st ON a.subject_id = st.subject_id
            WHERE st.teacher_id = %s
              AND sub.status IN ('submitted','in_review','resubmitted','notebook_sent')
        """, (user_id,)).fetchone()[0]
        overdue = conn.execute("""
            SELECT COUNT(*) FROM (
                SELECT a.id, st.id
                FROM assignments a
                JOIN subjects s ON a.subject_id = s.id
                JOIN subject_teachers st_link ON s.id = st_link.subject_id
                JOIN student_subjects ss ON ss.subject_id = s.id
                JOIN students st ON ss.student_id = st.id
                LEFT JOIN submissions sub ON sub.assignment_id = a.id AND sub.student_id = st.id
                WHERE st_link.teacher_id = %s
                  AND a.deadline < CURRENT_DATE
                  AND (
                      (COALESCE(a.submission_type, 'electronic') = 'electronic'
                       AND sub.id IS NOT NULL
                       AND (sub.status IS NULL OR sub.status NOT IN ('approved')))
                      OR
                      (a.submission_type = 'notebook'
                       AND (sub.status IS NULL OR sub.status NOT IN ('approved')))
                  )
            ) t
        """, (user_id,)).fetchone()[0]
        subjects = conn.execute(
            "SELECT COUNT(*) FROM subject_teachers WHERE teacher_id = %s", (user_id,)
        ).fetchone()[0]
    return {"pending": pending, "overdue": overdue, "subjects": subjects}


@router.get("/api/teacher/history/me")
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
                a.submission_type,
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


@router.get("/api/teacher/files/{assignment_id}/{student_id}")
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


@router.post("/api/teacher/grade")
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

        cur = conn.execute("""
            SELECT title, submission_type FROM assignments WHERE id = %s
        """, (assignment_id,))
        assignment_row = cur.fetchone()
        assignment_title = assignment_row["title"] if assignment_row else "Задание"
        is_notebook = (assignment_row["submission_type"] == "notebook") if assignment_row else False

        VALID_STATUSES = {"зачёт", "сдано", "не зачтено", "не допущен", "не сдано",
                          "принят на рассмотрение", "получена"}
        if status_input not in VALID_STATUSES:
            raise HTTPException(400, "Недопустимый статус")

        if status_input == "получена" and not is_notebook:
            raise HTTPException(400, "Статус «получена» применим только к тетрадным заданиям")

        if status_input == "не зачтено":
            cur = conn.execute("""
                SELECT id FROM submissions
                WHERE student_id = %s AND assignment_id = %s
            """, (student_id_int, assignment_id))
            submission_row = cur.fetchone()
            if submission_row and not is_notebook:
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
            "получена": "in_review",
            "принят на рассмотрение": "in_review"
        }
        db_status = status_mapping.get(status_input, "submitted")

        # Для тетрадных заданий создаём запись submission если её нет
        if is_notebook:
            conn.execute("""
                INSERT INTO submissions (student_id, assignment_id, status, submitted_at)
                VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (student_id, assignment_id) DO UPDATE SET status = %s, review = %s
            """, (student_id_int, assignment_id, db_status, db_status, review))
        else:
            conn.execute("""
                UPDATE submissions
                SET status = %s, review = %s
                WHERE student_id = %s AND assignment_id = %s
            """, (db_status, review, student_id_int, assignment_id))

        # "Получена" — только факт получения, итоговую оценку не выставляем
        if status_input != "получена":
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
        STATUS_EMAIL_LABELS = {
            "зачёт": "Зачтено",
            "сдано": "Зачтено",
            "не зачтено": "Не зачтено — требуется повторная сдача",
            "не допущен": "Не допущен",
            "не сдано": "Не зачтено",
            "получена": "Тетрадь получена преподавателем",
            "принят на рассмотрение": "Принято на рассмотрение",
        }
        status_label = STATUS_EMAIL_LABELS.get(status_input, status_input)
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


@router.post("/api/teacher/feedback/{assignment_id}/{student_id}")
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
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Тип файла «{ext}» не разрешён")
    if (file.size or 0) > MAX_FILE_SIZE:
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


@router.get("/api/teacher/progress")
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
