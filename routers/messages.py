"""
Личные сообщения студентам (чтение студентом, отправка преподавателем/админом).
"""

from fastapi import APIRouter, Form, Depends, HTTPException

from db import get_db
from auth import require_auth
from audit import write_audit

router = APIRouter()


@router.get("/api/messages/me")
async def get_my_messages(session = Depends(require_auth)):
    user_id, user_type = session
    if user_type != "student":
        raise HTTPException(403, "Доступ запрещён")
    with get_db() as conn:
        cur = conn.execute("""
            SELECT id, title, body, sender_type, sender_name, is_read, created_at
            FROM personal_messages
            WHERE student_id = %s
            ORDER BY created_at DESC
        """, (user_id,))
        rows = cur.fetchall()
    return [
        {
            "id": r["id"], "title": r["title"], "body": r["body"],
            "sender_type": r["sender_type"], "sender_name": r["sender_name"],
            "is_read": r["is_read"],
            "created_at": str(r["created_at"]),
        }
        for r in rows
    ]


@router.get("/api/messages/me/unread-count")
async def get_unread_count(session = Depends(require_auth)):
    user_id, user_type = session
    if user_type != "student":
        raise HTTPException(403, "Доступ запрещён")
    with get_db() as conn:
        cur = conn.execute("""
            SELECT COUNT(*) FROM personal_messages
            WHERE student_id = %s AND is_read = FALSE
        """, (user_id,))
        count = cur.fetchone()[0]
    return {"count": count}


@router.put("/api/messages/{msg_id}/read")
async def mark_message_read(msg_id: int, session = Depends(require_auth)):
    user_id, user_type = session
    if user_type != "student":
        raise HTTPException(403, "Доступ запрещён")
    with get_db() as conn:
        cur = conn.execute("""
            UPDATE personal_messages SET is_read = TRUE
            WHERE id = %s AND student_id = %s
        """, (msg_id, user_id))
    return {"message": "Прочитано"}


@router.post("/api/messages/send")
async def send_personal_message(
    student_id: int = Form(...),
    title: str = Form(...),
    body: str = Form(...),
    session = Depends(require_auth)
):
    user_id, user_type = session
    if user_type not in ("admin", "teacher"):
        raise HTTPException(403, "Доступ запрещён")
    if not title.strip() or len(title) > 200:
        raise HTTPException(400, "Тема: от 1 до 200 символов")
    if not body.strip() or len(body) > 10000:
        raise HTTPException(400, "Текст сообщения: от 1 до 10000 символов")

    with get_db() as conn:
        if user_type == "teacher":
            cur = conn.execute(
                "SELECT last_name, first_name FROM teachers WHERE id = %s", (user_id,)
            )
            row = cur.fetchone()
            sender_name = f"{row['last_name']} {row['first_name']}" if row else "Преподаватель"
        else:
            sender_name = "Администрация"

        st = conn.execute(
            "SELECT last_name, first_name, student_id FROM students WHERE id = %s", (student_id,)
        ).fetchone()
        if not st:
            raise HTTPException(404, "Студент не найден")

        # Преподаватель может писать только студентам со своих предметов
        if user_type == "teacher":
            allowed = conn.execute("""
                SELECT 1
                FROM student_subjects ss
                JOIN subject_teachers st_link ON st_link.subject_id = ss.subject_id
                WHERE ss.student_id = %s AND st_link.teacher_id = %s
                LIMIT 1
            """, (student_id, user_id)).fetchone()
            if not allowed:
                raise HTTPException(403, "Этот студент не учится на ваших предметах")

        conn.execute("""
            INSERT INTO personal_messages (student_id, title, body, sender_type, sender_name)
            VALUES (%s, %s, %s, %s, %s)
        """, (student_id, title.strip(), body.strip(), user_type, sender_name))

        if user_type == "admin":
            write_audit(conn, "Отправлено личное сообщение", "message", title.strip(),
                        f"Студент: {st['last_name']} {st['first_name']} ({st['student_id']})")

    return {"message": "Сообщение отправлено"}
