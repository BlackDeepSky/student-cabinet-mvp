"""
Скрипт для инициализации базы данных и загрузки тестовых данных.
Запуск: python seed_data.py
"""

import sqlite3
import os
from datetime import date

# Пути
DB_PATH = "instance/app.db"
SCHEMA_PATH = "schema.sql"

# Убедимся, что папка instance существует
os.makedirs("instance", exist_ok=True)

def init_db():
    """Создаёт структуру БД из schema.sql"""
    with sqlite3.connect(DB_PATH) as conn:
        with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
            conn.executescript(f.read())
        # Включаем поддержку внешних ключей
        conn.execute("PRAGMA foreign_keys = ON;")

def seed_data():
    """Загружает тестовые данные, избегая дублей"""
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()

        # --- Студенты ---
        students = [
            ("2023-IS-042", "Иванов", "Иван", "Иванович", "ivanov@example.com", "ИС-31"),
            ("2023-IS-043", "Петрова", "Мария", "Сергеевна", "petrova@example.com", "ИС-31"),
            ("2023-ЭК-115", "Сидоров", "Алексей", None, "sidorov@example.com", "ЭК-22"),
        ]
        for stud in students:
            cur.execute("""
                INSERT OR IGNORE INTO students 
                (student_id, last_name, first_name, patronymic, email, group_name)
                VALUES (?, ?, ?, ?, ?, ?)
            """, stud)

        # --- Предметы ---
        subjects = [
            ("Математика", "MATH101", "2025-1"),
            ("Программирование на Python", "CS102", "2025-1"),
            ("Экономика", "ECON101", "2025-1"),
        ]
        for subj in subjects:
            cur.execute("""
                INSERT OR IGNORE INTO subjects (name, code, semester)
                VALUES (?, ?, ?)
            """, subj)
        conn.commit()  # Гарантируем, что предметы записаны

        # --- Преподаватели ---
        teachers = [
            ("T-MATH-01", "Смирнов", "Пётр", "Алексеевич", "smirnov@example.com"),
            ("T-CS-02", "Козлова", "Елена", "Викторовна", "kozlova@example.com"),
        ]
        for teacher in teachers:
            cur.execute("""
                INSERT OR IGNORE INTO teachers (teacher_id, last_name, first_name, patronymic, email)
                VALUES (?, ?, ?, ?, ?)
            """, teacher)
        conn.commit()

        # --- Связи: кто ведёт какой предмет ---
        # Получаем ID преподавателей
        teacher_ids = {}
        for tid, _, _, _, _ in teachers:
            cur.execute("SELECT id FROM teachers WHERE teacher_id = ?", (tid,))
            row = cur.fetchone()
            if row:
                teacher_ids[tid] = row[0]

        # Получаем ID предметов по имени
        subject_name_to_id = {}
        cur.execute("SELECT id, name FROM subjects")
        for row in cur.fetchall():
            subject_name_to_id[row[1]] = row[0]

        # Проверяем наличие нужных предметов
        required_subjects = ["Математика", "Программирование на Python"]
        for subj in required_subjects:
            if subj not in subject_name_to_id:
                raise ValueError(f"Предмет '{subj}' отсутствует в таблице subjects.")

        # Вставляем связи
        subject_teacher_links = [
            ("Математика", "T-MATH-01"),
            ("Программирование на Python", "T-CS-02"),
        ]
        for subj_name, t_id in subject_teacher_links:
            s_id = subject_name_to_id[subj_name]
            t_id_int = teacher_ids[t_id]
            cur.execute("""
                INSERT OR IGNORE INTO subject_teachers (subject_id, teacher_id)
                VALUES (?, ?)
            """, (s_id, t_id_int))

        # --- Задания ---
        # Получаем ID предметов по коду
        subject_ids = {}
        for name, code, _ in subjects:
            cur.execute("SELECT id FROM subjects WHERE code = ?", (code,))
            row = cur.fetchone()
            if row:
                subject_ids[code] = row[0]

        assignments = [
            (subject_ids["MATH101"], "Контрольная работа №1", "Решить 10 задач", date(2025, 2, 10)),
            (subject_ids["CS102"], "Лабораторная №1", "Написать скрипт на Python", date(2025, 2, 15)),
            (subject_ids["CS102"], "Лабораторная №2", "Работа с файлами", date(2025, 2, 25)),
        ]
        for assignment in assignments:
            cur.execute("""
                INSERT OR IGNORE INTO assignments (subject_id, title, description, deadline)
                VALUES (?, ?, ?, ?)
            """, assignment)

        print("✅ Тестовые данные загружены.")

if __name__ == "__main__":
    print("Инициализация базы данных...")
    init_db()
    seed_data()
    print(f"База создана: {os.path.abspath(DB_PATH)}")