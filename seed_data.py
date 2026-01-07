"""
Инициализация базы данных и заполнение тестовыми данными
"""

import sqlite3
from pathlib import Path

# Определяем корень проекта и пути
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "instance" / "app.db"
SCHEMA_PATH = BASE_DIR / "schema.sql"

def init_db():
    """Создаёт таблицы из schema.sql"""
    if not SCHEMA_PATH.exists():
        raise FileNotFoundError(f"Файл схемы не найден: {SCHEMA_PATH}")
    
    with sqlite3.connect(DB_PATH) as conn:
        with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
            conn.executescript(f.read())
        conn.execute("PRAGMA foreign_keys = ON;")

def seed_data():
    """Создаёт БД и наполняет тестовыми данными"""
    # 1. Создаём таблицы
    init_db()

    # 2. Вставляем данные
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()

        # Студенты
        students = [
            ("2023-IS-042", "Иванов", "Иван", "Иванович", "ivanov@example.com", "ИС-31"),
            ("2023-IS-043", "Петрова", "Мария", "Сергеевна", "petrova@example.com", "ИС-31"),
            ("2023-ЭК-115", "Сидоров", "Алексей", None, "sidorov@example.com", "ЭК-22"),
        ]
        cur.executemany("""
            INSERT OR IGNORE INTO students 
            (student_id, last_name, first_name, patronymic, email, group_name)
            VALUES (?, ?, ?, ?, ?, ?)
        """, students)

        # Преподаватели
        teachers = [
            ("T-MATH-01", "Смирнов", "Пётр", "Алексеевич", "smirnov@example.com"),
            ("T-CS-02", "Козлова", "Елена", "Викторовна", "kozlova@example.com"),
        ]
        cur.executemany("""
            INSERT OR IGNORE INTO teachers 
            (teacher_id, last_name, first_name, patronymic, email)
            VALUES (?, ?, ?, ?, ?)
        """, teachers)

        # Предметы
        subjects = [
            ("Математика", "MATH101", "2025-1"),
            ("Программирование на Python", "CS102", "2025-1"),
            ("Экономика", "ECON101", "2025-1"),
        ]
        cur.executemany("""
            INSERT OR IGNORE INTO subjects (name, code, semester)
            VALUES (?, ?, ?)
        """, subjects)

        # Задания
        cur.execute("SELECT id FROM subjects")
        subject_ids = [row[0] for row in cur.fetchall()]
        if len(subject_ids) < 3:
            raise RuntimeError("Не удалось получить ID предметов")

        assignments = [
            (subject_ids[0], "Контрольная работа №1", "Решить 10 задач", "2026-02-01"),
            (subject_ids[1], "Лабораторная №1", "Написать программу", "2026-02-15"),
            (subject_ids[2], "Эссе", "Проанализировать рынок", "2026-03-01"),
        ]
        cur.executemany("""
            INSERT OR IGNORE INTO assignments (subject_id, title, description, deadline)
            VALUES (?, ?, ?, ?)
        """, assignments)

        # Связи преподавателей с предметами
        cur.execute("SELECT id, teacher_id FROM teachers")
        teacher_id_map = {tid: id for id, tid in cur.fetchall()}
        
        if "T-MATH-01" not in teacher_id_map or "T-CS-02" not in teacher_id_map:
            raise RuntimeError("Не удалось получить ID преподавателей")

        subject_teacher_links = [
            (subject_ids[0], teacher_id_map["T-MATH-01"]),
            (subject_ids[1], teacher_id_map["T-CS-02"]),
            (subject_ids[2], teacher_id_map["T-MATH-01"]),
        ]
        cur.executemany("""
            INSERT OR IGNORE INTO subject_teachers (subject_id, teacher_id)
            VALUES (?, ?)
        """, subject_teacher_links)

        # Автоматический коммит при выходе из контекста

def main():
    """Основная точка входа"""
    print("Инициализация базы данных...")
    try:
        seed_data()
        print("База данных успешно создана и заполнена.")
    except Exception as e:
        print(f"Ошибка при инициализации: {e}")
        raise

if __name__ == "__main__":
    main()