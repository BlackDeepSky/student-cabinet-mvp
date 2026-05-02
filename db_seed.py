"""
Инициализация базы данных и заполнение тестовыми данными (PostgreSQL)
"""

import os
from contextlib import closing
from pathlib import Path
import psycopg2
import bcrypt as _bcrypt


def hash_password(password: str) -> str:
    return _bcrypt.hashpw(password.encode("utf-8"), _bcrypt.gensalt()).decode("utf-8")


BASE_DIR = Path(__file__).resolve().parent
SCHEMA_PATH = BASE_DIR / "schema.sql"


def _get_database_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    if not url:
        raise RuntimeError("DATABASE_URL не задан в переменных окружения")
    return url


def get_connection():
    return psycopg2.connect(_get_database_url())


def init_db():
    """Создаёт таблицы из schema.sql"""
    if not SCHEMA_PATH.exists():
        raise FileNotFoundError(f"Файл схемы не найден: {SCHEMA_PATH}")

    with closing(get_connection()) as conn:
        with conn:
            with conn.cursor() as cur:
                with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
                    cur.execute(f.read())


def seed_data():
    """Создаёт БД и наполняет тестовыми данными"""
    init_db()

    with closing(get_connection()) as conn:
        with conn:
            with conn.cursor() as cur:
                # === Студенты ===
                students_raw = [
                    ("2023-IS-042", "Иванов", "Иван", "Иванович", "ivanov@example.com", "ИС-31", "2001-05-15", "15052001"),
                    ("2023-IS-043", "Петрова", "Мария", "Сергеевна", "petrova@example.com", "ИС-31", "2002-11-23", "23112002"),
                    ("2023-ЭК-115", "Сидоров", "Алексей", None, "sidorov@example.com", "ЭК-22", "2000-08-30", "30082000"),
                ]
                students = [
                    (sid, ln, fn, pat, email, grp, bd, hash_password(pwd))
                    for sid, ln, fn, pat, email, grp, bd, pwd in students_raw
                ]
                cur.executemany("""
                    INSERT INTO students
                    (student_id, last_name, first_name, patronymic, email, group_name, birth_date, password_hash)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT DO NOTHING
                """, students)

                # === Преподаватели ===
                teachers_raw = [
                    ("T-MATH-01", "Смирнов", "Пётр", "Алексеевич", "smirnov@example.com", "1975-03-12", "12031975"),
                    ("T-CS-02", "Козлова", "Елена", "Викторовна", "kozlova@example.com", "1982-07-19", "19071982"),
                ]
                teachers = [
                    (tid, ln, fn, pat, email, bd, hash_password(pwd))
                    for tid, ln, fn, pat, email, bd, pwd in teachers_raw
                ]
                cur.executemany("""
                    INSERT INTO teachers
                    (teacher_id, last_name, first_name, patronymic, email, birth_date, password_hash)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT DO NOTHING
                """, teachers)

                # === Предметы ===
                subjects = [
                    ("Математика", "MATH101", "2025-1"),
                    ("Программирование на Python", "CS102", "2025-1"),
                    ("Экономика", "ECON101", "2025-1"),
                ]
                cur.executemany("""
                    INSERT INTO subjects (name, code, semester)
                    VALUES (%s, %s, %s)
                    ON CONFLICT DO NOTHING
                """, subjects)

                # Получаем ID после вставки
                cur.execute("SELECT id, name FROM subjects")
                subject_map = {name: sid for sid, name in cur.fetchall()}

                cur.execute("SELECT id, teacher_id FROM teachers")
                teacher_map = {tid: pk for pk, tid in cur.fetchall()}

                cur.execute("SELECT id, student_id FROM students")
                student_map = {sid: pk for pk, sid in cur.fetchall()}

                # === Связь: студенты → предметы ===
                student_subject_links = [
                    (student_map["2023-IS-042"], subject_map["Математика"]),
                    (student_map["2023-IS-042"], subject_map["Программирование на Python"]),
                    (student_map["2023-IS-043"], subject_map["Математика"]),
                    (student_map["2023-ЭК-115"], subject_map["Экономика"]),
                ]
                cur.executemany("""
                    INSERT INTO student_subjects (student_id, subject_id)
                    VALUES (%s, %s)
                    ON CONFLICT DO NOTHING
                """, student_subject_links)

                # === Задания ===
                assignments = [
                    (subject_map["Математика"], "Контрольная работа №1", "Решить 10 задач", "2026-02-01"),
                    (subject_map["Программирование на Python"], "Лабораторная №1", "Написать программу", "2026-02-15"),
                    (subject_map["Экономика"], "Эссе", "Проанализировать рынок", "2026-03-01"),
                ]
                cur.executemany("""
                    INSERT INTO assignments (subject_id, title, description, deadline)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT DO NOTHING
                """, assignments)

                # === Связь: преподаватели → предметы ===
                subject_teacher_links = [
                    (subject_map["Математика"], teacher_map["T-MATH-01"]),
                    (subject_map["Программирование на Python"], teacher_map["T-CS-02"]),
                    (subject_map["Экономика"], teacher_map["T-MATH-01"]),
                ]
                cur.executemany("""
                    INSERT INTO subject_teachers (subject_id, teacher_id)
                    VALUES (%s, %s)
                    ON CONFLICT DO NOTHING
                """, subject_teacher_links)

                # === Администратор ===
                cur.execute("""
                    INSERT INTO admins (admin_id, password_hash)
                    VALUES (%s, %s)
                    ON CONFLICT DO NOTHING
                """, ("admin", hash_password("admin1234")))

                print("✅ Тестовые данные успешно добавлены.")


def main():
    """Основная точка входа"""
    print("Инициализация базы данных...")
    try:
        seed_data()
        print("✅ База данных готова к работе.")
    except Exception as e:
        print(f"❌ Ошибка при инициализации: {e}")
        raise


if __name__ == "__main__":
    main()
