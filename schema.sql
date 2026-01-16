-- Таблица студентов (с учётом ФИО и уникального student_id)
CREATE TABLE IF NOT EXISTS students (
    id           INTEGER PRIMARY KEY,
    student_id   TEXT NOT NULL UNIQUE,
    last_name    TEXT NOT NULL,
    first_name   TEXT NOT NULL,
    patronymic   TEXT,
    email        TEXT UNIQUE,
    group_name   TEXT,
    birth_date   TEXT,
    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Предметы
CREATE TABLE IF NOT EXISTS subjects (
    id       INTEGER PRIMARY KEY,
    name     TEXT NOT NULL UNIQUE,
    code     TEXT UNIQUE,
    semester TEXT
);

-- Задания
CREATE TABLE IF NOT EXISTS assignments (
    id          INTEGER PRIMARY KEY,
    subject_id  INTEGER NOT NULL,
    title       TEXT NOT NULL,
    description TEXT,
    deadline    DATE,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE CASCADE
);

-- Отправленные работы
CREATE TABLE IF NOT EXISTS submissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
    assignment_id INTEGER NOT NULL,
    status TEXT DEFAULT 'submitted',
    submitted_at TEXT,
    review TEXT,
    FOREIGN KEY (student_id) REFERENCES students(id),
    FOREIGN KEY (assignment_id) REFERENCES assignments(id),
    UNIQUE(student_id, assignment_id),
    CHECK (status IN ('submitted', 'in_review', 'rejected', 'approved', 'resubmitted'))
);

-- Файлы работ
CREATE TABLE IF NOT EXISTS submission_files (
    id            INTEGER PRIMARY KEY,
    submission_id INTEGER NOT NULL REFERENCES submissions(id) ON DELETE CASCADE,
    file_path     TEXT NOT NULL,
    uploaded_at   DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Успеваемость (итог по предмету)
CREATE TABLE IF NOT EXISTS grades (
    id          INTEGER PRIMARY KEY,
    student_id  INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    subject_id  INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    grade       INTEGER CHECK (grade BETWEEN 0 AND 100),
    status      TEXT DEFAULT 'не сдано',
    review      TEXT,
    graded_at   DATETIME DEFAULT CURRENT_TIMESTAMP,  -- ← НОВОЕ ПОЛЕ
    UNIQUE(student_id, subject_id)
);

-- Преподаватели
CREATE TABLE IF NOT EXISTS teachers (
    id         INTEGER PRIMARY KEY,
    teacher_id TEXT NOT NULL UNIQUE,
    last_name  TEXT NOT NULL,
    first_name TEXT NOT NULL,
    patronymic TEXT,
    birth_date TEXT,
    email      TEXT UNIQUE
);

-- Связь: кто ведёт какой предмет
CREATE TABLE IF NOT EXISTS subject_teachers (
    subject_id INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    teacher_id INTEGER NOT NULL REFERENCES teachers(id) ON DELETE CASCADE,
    PRIMARY KEY (subject_id, teacher_id)
);

-- Сессии пользователей
CREATE TABLE IF NOT EXISTS sessions (
    token       TEXT PRIMARY KEY,
    user_id     INTEGER NOT NULL,
    user_type   TEXT NOT NULL CHECK (user_type IN ('student', 'teacher')),
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    expires_at  DATETIME NOT NULL
);

-- Связь: студенты и предметы (учится ли студент на предмете)
CREATE TABLE IF NOT EXISTS student_subjects (
    student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    subject_id INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    PRIMARY KEY (student_id, subject_id)
);

CREATE TABLE IF NOT EXISTS teacher_feedback_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    submission_id INTEGER NOT NULL,
    file_path TEXT NOT NULL,
    uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (submission_id) REFERENCES submissions(id) ON DELETE CASCADE
);