"""
Скачивание файлов из R2 с проверкой прав доступа.
"""

import os

from fastapi import APIRouter, HTTPException, Depends

from db import get_db
from auth import require_auth
from storage import r2_stream

router = APIRouter()


@router.get("/download/{path:path}")
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

    return r2_stream(path, os.path.basename(path))
