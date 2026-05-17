-- Таблица студентов (с учётом ФИО и уникального student_id)
CREATE TABLE IF NOT EXISTS students (
    id             SERIAL PRIMARY KEY,
    student_id     TEXT NOT NULL UNIQUE,
    last_name      TEXT NOT NULL,
    first_name     TEXT NOT NULL,
    patronymic     TEXT,
    email          TEXT UNIQUE,
    group_name     TEXT,
    birth_date     TEXT,
    password_hash  TEXT NOT NULL DEFAULT '',
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Предметы
CREATE TABLE IF NOT EXISTS subjects (
    id       SERIAL PRIMARY KEY,
    name     TEXT NOT NULL UNIQUE,
    code     TEXT UNIQUE,
    semester TEXT
);

-- Задания
CREATE TABLE IF NOT EXISTS assignments (
    id              SERIAL PRIMARY KEY,
    subject_id      INTEGER NOT NULL,
    title           TEXT NOT NULL,
    description     TEXT,
    deadline        DATE,
    submission_type TEXT DEFAULT 'electronic' CHECK (submission_type IN ('electronic', 'notebook')),
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE CASCADE
);

-- Отправленные работы
CREATE TABLE IF NOT EXISTS submissions (
    id            SERIAL PRIMARY KEY,
    student_id    INTEGER NOT NULL,
    assignment_id INTEGER NOT NULL,
    status        TEXT DEFAULT 'submitted',
    submitted_at  TIMESTAMP,
    review        TEXT,
    FOREIGN KEY (student_id) REFERENCES students(id),
    FOREIGN KEY (assignment_id) REFERENCES assignments(id) ON DELETE CASCADE,
    UNIQUE(student_id, assignment_id),
    CHECK (status IN ('submitted', 'in_review', 'rejected', 'approved', 'resubmitted', 'notebook_sent'))
);

-- Файлы работ
CREATE TABLE IF NOT EXISTS submission_files (
    id            SERIAL PRIMARY KEY,
    submission_id INTEGER NOT NULL REFERENCES submissions(id) ON DELETE CASCADE,
    file_path     TEXT NOT NULL,
    uploaded_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Успеваемость (итог по предмету)
CREATE TABLE IF NOT EXISTS grades (
    id          SERIAL PRIMARY KEY,
    student_id  INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    subject_id  INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    grade       INTEGER CHECK (grade BETWEEN 0 AND 100),
    status      TEXT DEFAULT 'не сдано',
    review      TEXT,
    graded_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(student_id, subject_id)
);

-- Преподаватели
CREATE TABLE IF NOT EXISTS teachers (
    id            SERIAL PRIMARY KEY,
    teacher_id    TEXT NOT NULL UNIQUE,
    last_name     TEXT NOT NULL,
    first_name    TEXT NOT NULL,
    patronymic    TEXT,
    birth_date    TEXT,
    password_hash TEXT NOT NULL DEFAULT '',
    email         TEXT UNIQUE
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
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at  TIMESTAMP NOT NULL
);

-- Связь: студенты и предметы (учится ли студент на предмете)
CREATE TABLE IF NOT EXISTS student_subjects (
    student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    subject_id INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    PRIMARY KEY (student_id, subject_id)
);

CREATE TABLE IF NOT EXISTS teacher_feedback_files (
    id            SERIAL PRIMARY KEY,
    submission_id INTEGER NOT NULL,
    file_path     TEXT NOT NULL,
    uploaded_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (submission_id) REFERENCES submissions(id) ON DELETE CASCADE
);

-- Администраторы
CREATE TABLE IF NOT EXISTS admins (
    id            SERIAL PRIMARY KEY,
    admin_id      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Расширяем допустимые типы сессий для admin
DO $$
BEGIN
    ALTER TABLE sessions DROP CONSTRAINT IF EXISTS sessions_user_type_check;
    ALTER TABLE sessions ADD CONSTRAINT sessions_user_type_check
        CHECK (user_type IN ('student', 'teacher', 'admin'));
EXCEPTION WHEN duplicate_object THEN
    NULL;
END $$;

-- Миграция: тип сдачи задания и статус тетради
DO $$
BEGIN
    ALTER TABLE assignments ADD COLUMN IF NOT EXISTS submission_type TEXT DEFAULT 'electronic';
    ALTER TABLE submissions DROP CONSTRAINT IF EXISTS submissions_status_check;
    ALTER TABLE submissions ADD CONSTRAINT submissions_status_check
        CHECK (status IN ('submitted', 'in_review', 'rejected', 'approved', 'resubmitted', 'notebook_sent'));
EXCEPTION WHEN OTHERS THEN
    NULL;
END $$;

-- Миграция: каскадное удаление submissions при удалении assignment
DO $$
BEGIN
    ALTER TABLE submissions DROP CONSTRAINT IF EXISTS submissions_assignment_id_fkey;
    ALTER TABLE submissions ADD CONSTRAINT submissions_assignment_id_fkey
        FOREIGN KEY (assignment_id) REFERENCES assignments(id) ON DELETE CASCADE;
EXCEPTION WHEN OTHERS THEN
    NULL;
END $$;

-- Объявления (баннер для всех студентов)
CREATE TABLE IF NOT EXISTS announcements (
    id         SERIAL PRIMARY KEY,
    title      TEXT NOT NULL,
    body       TEXT NOT NULL,
    is_active  BOOLEAN DEFAULT TRUE,
    expires_at DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Личные сообщения студентам (от администратора или преподавателя)
CREATE TABLE IF NOT EXISTS personal_messages (
    id          SERIAL PRIMARY KEY,
    student_id  INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    title       TEXT NOT NULL,
    body        TEXT NOT NULL,
    sender_type TEXT NOT NULL CHECK (sender_type IN ('admin', 'teacher')),
    sender_name TEXT NOT NULL,
    is_read     BOOLEAN DEFAULT FALSE,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS admin_audit_log (
    id          SERIAL PRIMARY KEY,
    action      TEXT NOT NULL,
    entity      TEXT NOT NULL,
    entity_name TEXT,
    details     TEXT,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
