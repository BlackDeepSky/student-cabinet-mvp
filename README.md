# Личный кабинет заочного студента

Система управления учебными заданиями для студентов и преподавателей колледжей.

🔗 **Демо:** [https://student-cabinet-mvp.onrender.com](https://student-cabinet-mvp.onrender.com)

---

## Возможности

**Студент**
- Отправка заданий (несколько файлов)
- Отслеживание статусов: Отправлено → На рассмотрении → Зачтено / Не зачтено
- Просмотр рецензии и скачивание исправленной работы от преподавателя
- Таблица успеваемости

**Преподаватель**
- Просмотр и скачивание работ студентов
- Управление статусами и написание рецензий
- Отправка исправленного файла студенту
- Очистка файлов при повторной сдаче

---

## Стек

| Слой | Технология |
|---|---|
| Backend | Python 3.13, FastAPI |
| База данных | PostgreSQL (psycopg2) |
| Файловое хранилище | Cloudflare R2 (S3-совместимый) |
| Frontend | HTML, Bootstrap 5, vanilla JS |
| Деплой | Render |
| Безопасность | bcrypt (пароли), защита от path traversal |

---

## Локальный запуск

**1. Клонировать и создать виртуальное окружение**

```bash
git clone <repo-url>
cd student-cabinet-mvp
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

**2. Создать `.env` файл**

```bash
cp .env.example .env
```

Заполнить переменные:

```env
DATABASE_URL=postgresql://user:password@localhost:5432/student_cabinet

R2_ENDPOINT_URL=https://<ACCOUNT_ID>.r2.cloudflarestorage.com
R2_ACCESS_KEY_ID=your_access_key_id
R2_SECRET_ACCESS_KEY=your_secret_access_key
R2_BUCKET=student-cabinet
```

**3. Запустить**

```bash
uvicorn app:app --reload
```

База данных и тестовые данные создаются автоматически при первом запуске.

---

## Деплой на Render

В `render.yaml` описан сервис и база данных. При деплое нужно вручную добавить переменные окружения R2 в настройках сервиса на Render (они помечены `sync: false`).

---

## Тестовые данные

**Студенты**

| Логин | Пароль |
|---|---|
| 2023-IS-042 | 15052001 |
| 2023-IS-043 | 23112002 |

**Преподаватели**

| Логин | Пароль |
|---|---|
| T-MATH-01 | 12031975 |
| T-CS-02 | 19071982 |

---

## Структура БД

- `students` — студенты
- `teachers` — преподаватели
- `subjects` — дисциплины
- `subject_teachers` — связь преподаватель↔дисциплина
- `assignments` — задания
- `submissions` — отправленные работы (r2_key вместо локального пути)
- `grades` — успеваемость
