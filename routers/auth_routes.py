"""
Логины (студент/преподаватель/админ), смена пароля, бейдж уведомлений.
"""

from fastapi import APIRouter, Form, Depends, Request, HTTPException

from db import get_db
from auth import (
    check_rate_limit, validate_id, verify_password, hash_password,
    create_session, verify_session, require_auth, require_admin,
)

router = APIRouter()


@router.get("/api/badge")
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


@router.post("/api/login")
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


@router.post("/api/teacher/login")
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


@router.post("/api/admin/login")
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


@router.post("/api/change-password")
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


@router.post("/api/admin/change-password")
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
