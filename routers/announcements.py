"""
Объявления (баннер для студентов) и управление ими администратором.
"""

from typing import Optional

from fastapi import APIRouter, Form, Depends, HTTPException

from db import get_db
from auth import require_auth, require_admin
from audit import write_audit

router = APIRouter()


@router.get("/api/announcements/active")
async def get_active_announcement(session = Depends(require_auth)):
    with get_db() as conn:
        cur = conn.execute("""
            SELECT id, title, body, expires_at, created_at
            FROM announcements
            WHERE is_active = TRUE
              AND (expires_at IS NULL OR expires_at >= CURRENT_DATE)
            ORDER BY created_at DESC
            LIMIT 1
        """)
        row = cur.fetchone()
    if not row:
        return None
    return {
        "id": row["id"],
        "title": row["title"],
        "body": row["body"],
        "expires_at": str(row["expires_at"]) if row["expires_at"] else None,
        "created_at": str(row["created_at"]),
    }


@router.get("/api/admin/announcements")
async def admin_list_announcements(admin_id = Depends(require_admin)):
    with get_db() as conn:
        cur = conn.execute("""
            SELECT id, title, body, is_active, expires_at, created_at
            FROM announcements
            ORDER BY created_at DESC
        """)
        rows = cur.fetchall()
    return [
        {
            "id": r["id"], "title": r["title"], "body": r["body"],
            "is_active": r["is_active"],
            "expires_at": str(r["expires_at"]) if r["expires_at"] else None,
            "created_at": str(r["created_at"]),
        }
        for r in rows
    ]


@router.post("/api/admin/announcements")
async def admin_create_announcement(
    title: str = Form(...),
    body: str = Form(...),
    expires_at: Optional[str] = Form(None),
    admin_id = Depends(require_admin)
):
    if not title.strip() or len(title) > 200:
        raise HTTPException(400, "Заголовок: от 1 до 200 символов")
    if not body.strip() or len(body) > 5000:
        raise HTTPException(400, "Текст объявления: от 1 до 5000 символов")
    expires = expires_at if expires_at and expires_at.strip() else None
    with get_db() as conn:
        cur = conn.execute("""
            INSERT INTO announcements (title, body, expires_at)
            VALUES (%s, %s, %s)
            RETURNING id
        """, (title.strip(), body.strip(), expires))
        new_id = cur.fetchone()[0]
        write_audit(conn, "Создано объявление", "announcement", title.strip())
    return {"id": new_id, "message": "Объявление создано"}


@router.delete("/api/admin/announcements/{ann_id}")
async def admin_delete_announcement(ann_id: int, admin_id = Depends(require_admin)):
    with get_db() as conn:
        row = conn.execute("SELECT title FROM announcements WHERE id=%s", (ann_id,)).fetchone()
        if row:
            write_audit(conn, "Удалено объявление", "announcement", row["title"])
        conn.execute("DELETE FROM announcements WHERE id = %s", (ann_id,))
    return {"message": "Объявление удалено"}
