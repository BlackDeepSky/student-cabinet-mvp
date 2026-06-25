"""
Администрирование: статистика, аудит, экспорт, CRUD студентов/преподавателей/
предметов/заданий, зачисление и назначение.
"""

import csv
import io
import secrets
from urllib.parse import quote

from fastapi import APIRouter, Form, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from db import get_db
from auth import require_admin, validate_id, hash_password
from audit import write_audit

router = APIRouter()


# --- Аудит ---

@router.get("/api/admin/audit-log")
async def admin_audit_log_list(admin_id = Depends(require_admin)):
    with get_db() as conn:
        cur = conn.execute(
            "SELECT id, action, entity, entity_name, details, created_at FROM admin_audit_log ORDER BY created_at DESC LIMIT 500"
        )
        return [dict(r) for r in cur.fetchall()]


# --- Статистика ---

@router.get("/api/admin/stats")
async def admin_stats(admin_id = Depends(require_admin)):
    with get_db() as conn:
        students = conn.execute("SELECT COUNT(*) FROM students").fetchone()[0]
        teachers = conn.execute("SELECT COUNT(*) FROM teachers").fetchone()[0]
        pending = conn.execute("""
            SELECT COUNT(*) FROM submissions
            WHERE status IN ('submitted', 'in_review', 'resubmitted', 'notebook_sent')
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


@router.get("/api/admin/pending-details")
async def admin_pending_details(admin_id = Depends(require_admin)):
    with get_db() as conn:
        cur = conn.execute("""
            SELECT
                st.last_name || ' ' || st.first_name AS student_name,
                st.student_id,
                s.name AS subject,
                a.title AS assignment_title,
                a.submission_type,
                sub.status,
                sub.submitted_at,
                COALESCE(
                    (SELECT t2.last_name || ' ' || t2.first_name
                     FROM subject_teachers stl2
                     JOIN teachers t2 ON t2.id = stl2.teacher_id
                     WHERE stl2.subject_id = s.id
                     LIMIT 1),
                '—') AS teacher_name
            FROM submissions sub
            JOIN assignments a ON sub.assignment_id = a.id
            JOIN subjects s ON a.subject_id = s.id
            JOIN students st ON sub.student_id = st.id
            WHERE sub.status IN ('submitted', 'in_review', 'resubmitted', 'notebook_sent')
            ORDER BY sub.submitted_at ASC NULLS LAST
        """)
        return [dict(row) for row in cur.fetchall()]


@router.get("/api/admin/overdue-details")
async def admin_overdue_details(admin_id = Depends(require_admin)):
    with get_db() as conn:
        cur = conn.execute("""
            SELECT
                st.last_name || ' ' || st.first_name AS student_name,
                st.student_id,
                s.name AS subject,
                a.title AS assignment_title,
                a.deadline,
                COALESCE(
                    (SELECT t2.last_name || ' ' || t2.first_name
                     FROM subject_teachers stl2
                     JOIN teachers t2 ON t2.id = stl2.teacher_id
                     WHERE stl2.subject_id = s.id
                     LIMIT 1),
                '—') AS teacher_name
            FROM student_subjects ss
            JOIN assignments a ON a.subject_id = ss.subject_id
            JOIN subjects s ON a.subject_id = s.id
            JOIN students st ON ss.student_id = st.id
            WHERE a.deadline < CURRENT_DATE
              AND NOT EXISTS (
                  SELECT 1 FROM submissions sub
                  WHERE sub.student_id = ss.student_id
                    AND sub.assignment_id = a.id
                    AND sub.status = 'approved'
              )
            ORDER BY a.deadline ASC
        """)
        return [dict(row) for row in cur.fetchall()]


# --- Экспорт ---

@router.get("/api/admin/export/students")
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


@router.get("/api/admin/export/grades")
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
    STATUS_RU = {
        "submitted":     "Отправлено",
        "in_review":     "На проверке",
        "approved":      "Зачтено",
        "rejected":      "Не зачтено",
        "resubmitted":   "Повторно отправлено",
        "notebook_sent": "Тетрадь отправлена",
        "не сдано":      "Не сдано",
    }
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["ID студента", "Фамилия", "Имя", "Группа", "Предмет", "Задание", "Дедлайн", "Статус", "Дата сдачи"])
    for r in rows:
        deadline = r[6].strftime("%d.%m.%Y") if r[6] else ""
        submitted = r[8].strftime("%d.%m.%Y %H:%M") if r[8] else ""
        status_ru = STATUS_RU.get(r[7], r[7])
        w.writerow([r[0], r[1], r[2], r[3] or "", r[4], r[5], deadline, status_ru, submitted])
    buf.seek(0)
    fname = quote("успеваемость студентов.csv")
    return StreamingResponse(iter([buf.getvalue().encode("utf-8-sig")]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{fname}"})


# --- Студенты ---

@router.get("/api/admin/students")
async def admin_list_students(admin_id = Depends(require_admin)):
    with get_db() as conn:
        cur = conn.execute("""
            SELECT id, student_id, last_name, first_name, patronymic, group_name, email
            FROM students ORDER BY last_name, first_name
        """)
        return [dict(r) for r in cur.fetchall()]


@router.post("/api/admin/students")
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
        write_audit(conn, "Добавлен студент", "student", f"{last_name} {first_name} ({clean_id})")
    return {"ok": True, "temp_password": temp_password}


@router.put("/api/admin/students/{student_db_id}")
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
        cur = conn.execute("SELECT student_id FROM students WHERE id = %s", (student_db_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Студент не найден")
        conn.execute("""
            UPDATE students SET last_name=%s, first_name=%s, patronymic=%s, group_name=%s, email=%s
            WHERE id=%s
        """, (last_name, first_name, patronymic or None, group_name or None, email or None, student_db_id))
        write_audit(conn, "Изменён студент", "student", f"{last_name} {first_name} ({row['student_id']})")
    return {"ok": True}


@router.post("/api/admin/students/{student_db_id}/reset-password")
async def admin_reset_student_password(student_db_id: int, admin_id = Depends(require_admin)):
    with get_db() as conn:
        cur = conn.execute("SELECT student_id, last_name, first_name FROM students WHERE id = %s", (student_db_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Студент не найден")
        temp_password = secrets.token_hex(4)
        conn.execute("UPDATE students SET password_hash = %s WHERE id = %s",
                     (hash_password(temp_password), student_db_id))
        write_audit(conn, "Сброс пароля студента", "student", f"{row['last_name']} {row['first_name']} ({row['student_id']})")
    return {"ok": True, "temp_password": temp_password}


@router.delete("/api/admin/students/{student_db_id}")
async def admin_delete_student(student_db_id: int, admin_id = Depends(require_admin)):
    with get_db() as conn:
        cur = conn.execute("SELECT student_id, last_name, first_name FROM students WHERE id = %s", (student_db_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Студент не найден")
        write_audit(conn, "Удалён студент", "student", f"{row['last_name']} {row['first_name']} ({row['student_id']})")
        conn.execute("DELETE FROM students WHERE id = %s", (student_db_id,))
    return {"ok": True}


# --- Преподаватели ---

@router.get("/api/admin/teachers")
async def admin_list_teachers(admin_id = Depends(require_admin)):
    with get_db() as conn:
        cur = conn.execute("""
            SELECT id, teacher_id, last_name, first_name, patronymic, email
            FROM teachers ORDER BY last_name, first_name
        """)
        return [dict(r) for r in cur.fetchall()]


@router.post("/api/admin/teachers")
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
        write_audit(conn, "Добавлен преподаватель", "teacher", f"{last_name} {first_name} ({clean_id})")
    return {"ok": True, "temp_password": temp_password}


@router.put("/api/admin/teachers/{teacher_db_id}")
async def admin_edit_teacher(
    teacher_db_id: int,
    last_name: str = Form(...),
    first_name: str = Form(...),
    patronymic: str = Form(None),
    email: str = Form(None),
    admin_id = Depends(require_admin)
):
    with get_db() as conn:
        cur = conn.execute("SELECT teacher_id FROM teachers WHERE id = %s", (teacher_db_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Преподаватель не найден")
        conn.execute("""
            UPDATE teachers SET last_name=%s, first_name=%s, patronymic=%s, email=%s
            WHERE id=%s
        """, (last_name, first_name, patronymic or None, email or None, teacher_db_id))
        write_audit(conn, "Изменён преподаватель", "teacher", f"{last_name} {first_name} ({row['teacher_id']})")
    return {"ok": True}


@router.post("/api/admin/teachers/{teacher_db_id}/reset-password")
async def admin_reset_teacher_password(teacher_db_id: int, admin_id = Depends(require_admin)):
    with get_db() as conn:
        cur = conn.execute("SELECT teacher_id, last_name, first_name FROM teachers WHERE id = %s", (teacher_db_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Преподаватель не найден")
        temp_password = secrets.token_hex(4)
        conn.execute("UPDATE teachers SET password_hash = %s WHERE id = %s",
                     (hash_password(temp_password), teacher_db_id))
        write_audit(conn, "Сброс пароля преподавателя", "teacher", f"{row['last_name']} {row['first_name']} ({row['teacher_id']})")
    return {"ok": True, "temp_password": temp_password}


@router.delete("/api/admin/teachers/{teacher_db_id}")
async def admin_delete_teacher(teacher_db_id: int, admin_id = Depends(require_admin)):
    with get_db() as conn:
        cur = conn.execute("SELECT teacher_id, last_name, first_name FROM teachers WHERE id = %s", (teacher_db_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Преподаватель не найден")
        write_audit(conn, "Удалён преподаватель", "teacher", f"{row['last_name']} {row['first_name']} ({row['teacher_id']})")
        conn.execute("DELETE FROM teachers WHERE id = %s", (teacher_db_id,))
    return {"ok": True}


# --- Предметы ---

@router.get("/api/admin/subjects")
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


@router.post("/api/admin/subjects")
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
            new_id = cur.fetchone()[0]
        except Exception:
            raise HTTPException(400, "Предмет с таким названием уже существует")
        write_audit(conn, "Добавлен предмет", "subject", name)
        return {"ok": True, "id": new_id}


@router.delete("/api/admin/subjects/{subject_id}")
async def admin_delete_subject(subject_id: int, admin_id = Depends(require_admin)):
    with get_db() as conn:
        cur = conn.execute("SELECT name FROM subjects WHERE id = %s", (subject_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Предмет не найден")
        write_audit(conn, "Удалён предмет", "subject", row["name"])
        conn.execute("DELETE FROM subjects WHERE id = %s", (subject_id,))
    return {"ok": True}


@router.post("/api/admin/subjects/{subject_id}/teachers")
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
        s = conn.execute("SELECT name FROM subjects WHERE id=%s", (subject_id,)).fetchone()
        t = conn.execute("SELECT last_name, first_name FROM teachers WHERE id=%s", (teacher_id,)).fetchone()
        if s and t:
            write_audit(conn, "Назначен преподаватель на предмет", "subject",
                        s["name"], f"Преподаватель: {t['last_name']} {t['first_name']}")
    return {"ok": True}


@router.delete("/api/admin/subjects/{subject_id}/teachers/{teacher_id}")
async def admin_remove_teacher(subject_id: int, teacher_id: int, admin_id = Depends(require_admin)):
    with get_db() as conn:
        s = conn.execute("SELECT name FROM subjects WHERE id=%s", (subject_id,)).fetchone()
        t = conn.execute("SELECT last_name, first_name FROM teachers WHERE id=%s", (teacher_id,)).fetchone()
        conn.execute("DELETE FROM subject_teachers WHERE subject_id = %s AND teacher_id = %s",
                     (subject_id, teacher_id))
        if s and t:
            write_audit(conn, "Снят преподаватель с предмета", "subject",
                        s["name"], f"Преподаватель: {t['last_name']} {t['first_name']}")
    return {"ok": True}


@router.post("/api/admin/subjects/{subject_id}/students")
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
        s = conn.execute("SELECT name FROM subjects WHERE id=%s", (subject_id,)).fetchone()
        st = conn.execute("SELECT last_name, first_name, student_id FROM students WHERE id=%s", (student_id,)).fetchone()
        if s and st:
            write_audit(conn, "Студент зачислен на предмет", "subject",
                        s["name"], f"Студент: {st['last_name']} {st['first_name']} ({st['student_id']})")
    return {"ok": True}


@router.post("/api/admin/subjects/{subject_id}/students/bulk")
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
        s = conn.execute("SELECT name FROM subjects WHERE id=%s", (subject_id,)).fetchone()
        if s:
            write_audit(conn, "Массовое зачисление на предмет", "subject",
                        s["name"], f"Зачислено студентов: {len(student_ids)}")
    return {"ok": True, "enrolled": len(student_ids)}


@router.delete("/api/admin/subjects/{subject_id}/students/{student_id}")
async def admin_unenroll_student(subject_id: int, student_id: int, admin_id = Depends(require_admin)):
    with get_db() as conn:
        s = conn.execute("SELECT name FROM subjects WHERE id=%s", (subject_id,)).fetchone()
        st = conn.execute("SELECT last_name, first_name, student_id FROM students WHERE id=%s", (student_id,)).fetchone()
        conn.execute("DELETE FROM student_subjects WHERE student_id = %s AND subject_id = %s",
                     (student_id, subject_id))
        if s and st:
            write_audit(conn, "Студент отчислен с предмета", "subject",
                        s["name"], f"Студент: {st['last_name']} {st['first_name']} ({st['student_id']})")
    return {"ok": True}


@router.get("/api/admin/subjects/{subject_id}/members")
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

@router.get("/api/admin/assignments")
async def admin_list_assignments(admin_id = Depends(require_admin)):
    with get_db() as conn:
        cur = conn.execute("""
            SELECT a.id, a.subject_id, a.title, a.description, a.deadline,
                   a.submission_type, s.name AS subject
            FROM assignments a JOIN subjects s ON s.id = a.subject_id
            ORDER BY a.deadline DESC NULLS LAST
        """)
        rows = []
        for r in cur.fetchall():
            d = dict(r)
            d["deadline"] = d["deadline"].strftime("%Y-%m-%d") if d["deadline"] else None
            rows.append(d)
        return rows


@router.post("/api/admin/assignments")
async def admin_add_assignment(
    subject_id: int = Form(...),
    title: str = Form(...),
    description: str = Form(None),
    deadline: str = Form(None),
    submission_type: str = Form("electronic"),
    admin_id = Depends(require_admin)
):
    if submission_type not in ("electronic", "notebook"):
        submission_type = "electronic"
    with get_db() as conn:
        cur = conn.execute("""
            INSERT INTO assignments (subject_id, title, description, deadline, submission_type)
            VALUES (%s, %s, %s, %s, %s) RETURNING id
        """, (subject_id, title, description or None, deadline or None, submission_type))
        new_id = cur.fetchone()[0]
        s = conn.execute("SELECT name FROM subjects WHERE id=%s", (subject_id,)).fetchone()
        write_audit(conn, "Добавлено задание", "assignment", title,
                    f"Предмет: {s['name']}" if s else None)
        return {"ok": True, "id": new_id}


@router.put("/api/admin/assignments/{assignment_id}")
async def admin_edit_assignment(
    assignment_id: int,
    subject_id: int = Form(...),
    title: str = Form(...),
    description: str = Form(None),
    deadline: str = Form(None),
    submission_type: str = Form("electronic"),
    admin_id = Depends(require_admin)
):
    if submission_type not in ("electronic", "notebook"):
        submission_type = "electronic"
    with get_db() as conn:
        cur = conn.execute("SELECT id FROM assignments WHERE id = %s", (assignment_id,))
        if not cur.fetchone():
            raise HTTPException(404, "Задание не найдено")
        conn.execute("""
            UPDATE assignments SET subject_id=%s, title=%s, description=%s, deadline=%s, submission_type=%s
            WHERE id=%s
        """, (subject_id, title, description or None, deadline or None, submission_type, assignment_id))
        s = conn.execute("SELECT name FROM subjects WHERE id=%s", (subject_id,)).fetchone()
        write_audit(conn, "Изменено задание", "assignment", title,
                    f"Предмет: {s['name']}" if s else None)
    return {"ok": True}


@router.delete("/api/admin/assignments/{assignment_id}")
async def admin_delete_assignment(assignment_id: int, admin_id = Depends(require_admin)):
    with get_db() as conn:
        cur = conn.execute("""
            SELECT a.title, s.name AS subject_name FROM assignments a
            JOIN subjects s ON a.subject_id = s.id WHERE a.id = %s
        """, (assignment_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Задание не найдено")
        write_audit(conn, "Удалено задание", "assignment", row["title"],
                    f"Предмет: {row['subject_name']}")
        conn.execute("DELETE FROM assignments WHERE id = %s", (assignment_id,))
    return {"ok": True}
