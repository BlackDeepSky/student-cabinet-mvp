-- Преподаватели
CREATE TABLE IF NOT EXISTS teachers (
    id         INTEGER PRIMARY KEY,
    teacher_id TEXT NOT NULL UNIQUE,  -- например: T-MATH-01
    last_name  TEXT NOT NULL,
    first_name TEXT NOT NULL,
    patronymic TEXT,
    email      TEXT UNIQUE
);

-- Связь: кто ведёт какой предмет
CREATE TABLE IF NOT EXISTS subject_teachers (
    subject_id INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    teacher_id INTEGER NOT NULL REFERENCES teachers(id) ON DELETE CASCADE,
    PRIMARY KEY (subject_id, teacher_id)
);

-- Таблица студентов (с учётом ФИО и уникального student_id)
CREATE TABLE IF NOT EXISTS students (
    id           INTEGER PRIMARY KEY,
    student_id   TEXT NOT NULL UNIQUE,
    last_name    TEXT NOT NULL,
    first_name   TEXT NOT NULL,
    patronymic   TEXT,
    email        TEXT UNIQUE,
    group_name   TEXT,
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
    id            INTEGER PRIMARY KEY,
    student_id    INTEGER NOT NULL,
    assignment_id INTEGER NOT NULL,
    file_path     TEXT NOT NULL,
    submitted_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    status        TEXT DEFAULT 'submitted',
    FOREIGN KEY (student_id)    REFERENCES students(id)    ON DELETE CASCADE,
    FOREIGN KEY (assignment_id) REFERENCES assignments(id) ON DELETE CASCADE,
    UNIQUE(student_id, assignment_id)
);

-- Успеваемость (итог по предмету)
CREATE TABLE IF NOT EXISTS grades (
    id          INTEGER PRIMARY KEY,
    student_id  INTEGER NOT NULL,
    subject_id  INTEGER NOT NULL,
    grade       INTEGER CHECK (grade BETWEEN 0 AND 100),
    status      TEXT DEFAULT 'не сдано',
    updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (student_id)  REFERENCES students(id) ON DELETE CASCADE,
    FOREIGN KEY (subject_id)  REFERENCES subjects(id) ON DELETE CASCADE,
    UNIQUE(student_id, subject_id)
);