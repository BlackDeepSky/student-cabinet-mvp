<h1 align="center">КабинетЗаочника</h1>

<p align="center">
  <strong>SaaS для автоматизации сдачи учебных работ в колледжах Беларуси</strong><br>
  Студент отправляет работы → Преподаватель проверяет → Все без лишних звонков
</p>

<p align="center">
  <a href="https://student-cabinet-mvp.onrender.com">
    <img src="https://img.shields.io/badge/demo-live-brightgreen?style=for-the-badge" alt="Demo">
  </a>
  <img src="https://img.shields.io/badge/python-3.13-blue?style=for-the-badge&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/FastAPI-0.115-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/PostgreSQL-neon.tech-4169E1?style=for-the-badge&logo=postgresql&logoColor=white" alt="PostgreSQL">
</p>

---

## Зачем это нужно

Студенты-заочники колледжей сдают работы преподавателям несколькими способами: электронные файлы по почте, тетради почтой, личная встреча. Без единой системы это — хаос: потерянные письма, бесконечные звонки «получили ли вы мою работу?», ручное отслеживание статусов.

**КабинетЗаочника** объединяет всё в одном месте.

---

## Возможности

### Студент
- Сдача работ в электронном виде (до 10 файлов: PDF, DOCX, XLSX, ZIP, PNG, JPG и др.)
- Сдача тетрадных работ почтой — отметить отправку в кабинете одной кнопкой
- Статусы в реальном времени: Отправлено → На рассмотрении → Зачтено / Не зачтено
- Повторная сдача после отклонения
- Рецензия и файл обратной связи от преподавателя прямо в карточке
- Таблица успеваемости по предметам
- Цветовая индикация дедлайнов (зелёный / жёлтый / красный)
- Смена пароля в профиле
- PWA: установка на домашний экран, badge-уведомления на иконке

### Преподаватель
- Список работ на проверку с сортировкой по дедлайну
- Просмотр и скачивание файлов студента
- Выставление статуса + рецензия + опциональный файл обратной связи
- Поддержка тетрадных работ: три статуса — «Зачтено», «Не зачтено», «Нет в кабинете»
- Общий прогресс студентов по предметам (таблица с фильтром)
- История зачтённых работ
- Смена пароля в профиле

### Администратор
- CRUD: студенты, преподаватели, предметы, задания
- Тип задания при создании: **электронное** или **в тетради (почтой)**
- Назначение преподавателей на предметы
- Массовая запись студентов на предмет (по группе)
- Поиск и фильтр по всем разделам
- Дашборд: студентов / преподавателей / на проверке / просрочено
- Сброс пароля любого пользователя
- Экспорт успеваемости в CSV

---

## Стек

| Слой | Технология |
|---|---|
| Backend | Python 3.13, FastAPI |
| База данных | PostgreSQL — [neon.tech](https://neon.tech) |
| Файловое хранилище | Cloudflare R2 (S3-совместимый) |
| Frontend | HTML + Bootstrap 5 + vanilla JS |
| Безопасность | bcrypt, rate limiting, CORS, path traversal protection |
| PWA | manifest.json + service worker |
| Email | SMTP (уведомления об изменении статуса) |
| Деплой | [Render](https://render.com) |

---

## Локальный запуск

**1. Клонировать репозиторий**

```bash
git clone https://github.com/BlackDeepSky/student-cabinet-mvp.git
cd student-cabinet-mvp
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

**2. Создать `.env`**

```bash
cp .env.example .env
```

Заполнить переменные в `.env`:

```env
DATABASE_URL=postgresql://user:password@localhost:5432/student_cabinet

R2_ENDPOINT_URL=https://<ACCOUNT_ID>.r2.cloudflarestorage.com
R2_ACCESS_KEY_ID=your_access_key
R2_SECRET_ACCESS_KEY=your_secret_key
R2_BUCKET=student-cabinet

SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your@gmail.com
SMTP_PASSWORD=app_password
```

**3. Запустить**

```bash
uvicorn app:app --reload
```

База данных и тестовые данные создаются автоматически при первом запуске (`db_seed.py`).

---

## Деплой на Render

`render.yaml` уже настроен. При деплое добавьте переменные `R2_*` и `SMTP_*` вручную в настройках сервиса (они помечены `sync: false` намеренно — чтобы секреты не попали в репозиторий).

---

## Тестовые данные

> Доступны на [демо-стенде](https://student-cabinet-mvp.onrender.com)

**Студенты** — вход через `/`

| Логин | Пароль |
|---|---|
| 2023-IS-042 | 15052001 |
| 2023-IS-043 | 23112002 |

**Преподаватели** — вход через `/teacher`

| Логин | Пароль |
|---|---|
| T-MATH-01 | 12031975 |
| T-CS-02 | 19071982 |

**Администратор** — вход через `/admin`

| Логин | Пароль |
|---|---|
| admin | admin1234 |

---

## Структура базы данных

```
students              — студенты
teachers              — преподаватели
admins                — администраторы
subjects              — дисциплины
subject_teachers      — преподаватель ↔ дисциплина
student_subjects      — студент ↔ дисциплина
assignments           — задания (тип: electronic | notebook)
submissions           — сданные работы (статусы: submitted, in_review, rejected, approved, resubmitted, notebook_sent)
submission_files      — файлы работ студента (ключи R2)
teacher_feedback_files— файлы обратной связи преподавателя (ключи R2)
grades                — итоговая успеваемость по предмету
sessions              — активные сессии (student | teacher | admin)
```

---

## Безопасность

- Пароли хешируются через **bcrypt**
- Rate limiting на эндпоинтах входа (10 попыток / IP / 60 сек)
- Защита от path traversal при скачивании файлов
- Whitelist расширений загружаемых файлов
- Проверка владельца файла через БД (IDOR-защита)
- Смена пароля инвалидирует все активные сессии пользователя
- CORS с allowlist доменов через переменную окружения
- XSS-защита: экранирование всего пользовательского контента через `escapeHtml()`
