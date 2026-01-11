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

        # === Студенты ===
        students = [
            ("2023-IS-042", "Иванов", "Иван", "Иванович", "ivanov@example.com", "ИС-31", "2001-05-15"),
            ("2023-IS-043", "Петрова", "Мария", "Сергеевна", "petrova@example.com", "ИС-31", "2002-11-23"),
            ("2023-ЭК-115", "Сидоров", "Алексей", None, "sidorov@example.com", "ЭК-22", "2000-08-30"),
        ]
        cur.executemany("""
            INSERT OR IGNORE INTO students 
            (student_id, last_name, first_name, patronymic, email, group_name, birth_date)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, students)

        # === Преподаватели ===
        teachers = [
            ("T-MATH-01", "Смирнов", "Пётр", "Алексеевич", "smirnov@example.com", "1975-03-12"),
            ("T-CS-02", "Козлова", "Елена", "Викторовна", "kozlova@example.com", "1982-07-19"),
        ]
        cur.executemany("""
            INSERT OR IGNORE INTO teachers 
            (teacher_id, last_name, first_name, patronymic, email, birth_date)
            VALUES (?, ?, ?, ?, ?, ?)
        """, teachers)

        # === Предметы ===
        subjects = [
            ("Математика", "MATH101", "2025-1"),
            ("Программирование на Python", "CS102", "2025-1"),
            ("Экономика", "ECON101", "2025-1"),
        ]
        cur.executemany("""
            INSERT OR IGNORE INTO subjects (name, code, semester)
            VALUES (?, ?, ?)
        """, subjects)

        # Получаем ID после вставки
        cur.execute("SELECT id, name FROM subjects")
        subject_map = {name: id for id, name in cur.fetchall()}

        cur.execute("SELECT id, teacher_id FROM teachers")
        teacher_map = {tid: id for id, tid in cur.fetchall()}

        cur.execute("SELECT id, student_id FROM students")
        student_map = {sid: id for id, sid in cur.fetchall()}

        # === Связь: студенты → предметы ===
        student_subject_links = [
            (student_map["2023-IS-042"], subject_map["Математика"]),
            (student_map["2023-IS-042"], subject_map["Программирование на Python"]),
            (student_map["2023-IS-043"], subject_map["Математика"]),
            (student_map["2023-ЭК-115"], subject_map["Экономика"]),
        ]
        cur.executemany("""
            INSERT OR IGNORE INTO student_subjects (student_id, subject_id)
            VALUES (?, ?)
        """, student_subject_links)

        # === Задания ===
        assignments = [
            (subject_map["Математика"], "Контрольная работа №1", "Решить 10 задач", "2026-02-01"),
            (subject_map["Программирование на Python"], "Лабораторная №1", "Написать программу", "2026-02-15"),
            (subject_map["Экономика"], "Эссе", "Проанализировать рынок", "2026-03-01"),
        ]
        cur.executemany("""
            INSERT OR IGNORE INTO assignments (subject_id, title, description, deadline)
            VALUES (?, ?, ?, ?)
        """, assignments)

        # === Связь: преподаватели → предметы ===
        subject_teacher_links = [
            (subject_map["Математика"], teacher_map["T-MATH-01"]),
            (subject_map["Программирование на Python"], teacher_map["T-CS-02"]),
            (subject_map["Экономика"], teacher_map["T-MATH-01"]),
        ]
        cur.executemany("""
            INSERT OR IGNORE INTO subject_teachers (subject_id, teacher_id)
            VALUES (?, ?)
        """, subject_teacher_links)

        print("✅ Тестовые данные успешно добавлены.")

def main():
    """Основная точка входа"""
    print("Инициализация базы данных...")
    try:
        DB_PATH.parent.mkdir(exist_ok=True)
        seed_data()
        print("✅ База данных готова к работе.")
    except Exception as e:
        print(f"❌ Ошибка при инициализации: {e}")
        raise

if __name__ == "__main__":
    main()