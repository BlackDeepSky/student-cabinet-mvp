# seed_data.py
import sqlite3
import os
from pathlib import Path

DB_PATH = Path("instance/app.db")

def init_db():
    """Создаёт таблицы из schema.sql"""
    conn = sqlite3.connect(DB_PATH)
    schema_path = Path("schema.sql")
    with open(schema_path, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.commit()
    conn.close()

def seed_data():
    """Создаёт БД и наполняет тестовыми данными"""
    # 1. Создаём таблицы
    init_db()

    # 2. Вставляем данные
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Студенты
    students = [
        ("2023-IS-042", "Иванов", "Иван", "Иванович", "ivanov@example.com", "ИС-31"),
        ("2023-IS-043", "Петрова", "Мария", "Сергеевна", "petrova@example.com", "ИС-31"),
        ("2023-ЭК-115", "Сидоров", "Алексей", None, "sidorov@example.com", "ЭК-22"),
    ]
    cur.executemany("""
        INSERT OR IGNORE INTO students (student_id, last_name, first_name, patronymic, email, group_name)
        VALUES (?, ?, ?, ?, ?, ?)
    """, students)

    # Преподаватели
    teachers = [
        ("T-MATH-01", "Смирнов", "Пётр", "Алексеевич", "smirnov@example.com"),
        ("T-CS-02", "Козлова", "Елена", "Викторовна", "kozlova@example.com"),
    ]
    cur.executemany("""
        INSERT OR IGNORE INTO teachers (teacher_id, last_name, first_name, patronymic, email)
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
    # Получаем ID преподавателей
    cur.execute("SELECT id, teacher_id FROM teachers")
    teacher_id_map = {tid: id for id, tid in cur.fetchall()}
    
    subject_teacher_links = [
        (subject_ids[0], teacher_id_map["T-MATH-01"]),
        (subject_ids[1], teacher_id_map["T-CS-02"]),
        (subject_ids[2], teacher_id_map["T-MATH-01"]),
    ]
    cur.executemany("""
        INSERT OR IGNORE INTO subject_teachers (subject_id, teacher_id)
        VALUES (?, ?)
    """, subject_teacher_links)

    conn.commit()
    conn.close()

if __name__ == "__main__":
    seed_data()