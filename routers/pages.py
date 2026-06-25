"""
Отдача HTML-страниц и service worker.
"""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, FileResponse

router = APIRouter()

_NO_CACHE = {"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache"}


@router.get("/", response_class=HTMLResponse)
async def landing_page():
    with open("static/landing.html", encoding="utf-8") as f:
        return HTMLResponse(f.read(), headers=_NO_CACHE)


@router.get("/student", response_class=HTMLResponse)
async def student_page():
    with open("static/student.html", encoding="utf-8") as f:
        return HTMLResponse(f.read(), headers=_NO_CACHE)


@router.get("/teacher", response_class=HTMLResponse)
async def teacher_page():
    with open("static/teacher.html", encoding="utf-8") as f:
        return HTMLResponse(f.read(), headers=_NO_CACHE)


@router.get("/admin", response_class=HTMLResponse)
async def admin_page():
    with open("static/admin.html", encoding="utf-8") as f:
        return HTMLResponse(f.read(), headers=_NO_CACHE)


@router.get("/sw.js")
async def service_worker():
    return FileResponse("static/sw.js", media_type="application/javascript")
