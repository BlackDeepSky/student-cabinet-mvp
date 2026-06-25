"""
Подключение к PostgreSQL: пул соединений и обёртка с интерфейсом conn.execute(...).
"""

import os
from psycopg2.extras import DictCursor
from psycopg2.pool import ThreadedConnectionPool

# === Настройка БД ===
DATABASE_URL = os.environ.get("DATABASE_URL", "")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

_pool: "ThreadedConnectionPool | None" = None


def _make_pool() -> "ThreadedConnectionPool":
    return ThreadedConnectionPool(
        minconn=1,
        maxconn=10,
        dsn=DATABASE_URL,
        # TCP keepalives — не даём Neon закрыть соединение со своей стороны молча
        keepalives=1,
        keepalives_idle=60,
        keepalives_interval=10,
        keepalives_count=3,
    )


def _get_pool() -> "ThreadedConnectionPool":
    global _pool
    if _pool is None or _pool.closed:
        _pool = _make_pool()
    return _pool


class DBConnection:
    """Обёртка над psycopg2: интерфейс conn.execute(...) → cursor с fetch* и dict-доступом."""

    def __init__(self, conn, pool: "ThreadedConnectionPool"):
        self._conn = conn
        self._pool = pool

    def execute(self, query, params=None):
        cur = self._conn.cursor(cursor_factory=DictCursor)
        if params is None:
            cur.execute(query)
        else:
            cur.execute(query, params)
        return cur

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        broken = False
        try:
            if exc_type is None:
                self._conn.commit()
            else:
                self._conn.rollback()
        except Exception:
            broken = True
        finally:
            # broken или ошибочный коннект — выбрасываем из пула, остальные возвращаем
            self._pool.putconn(self._conn, close=broken)
        return False


def get_db():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL не задан в переменных окружения")
    pool = _get_pool()
    conn = pool.getconn()
    # Если коннект протух (Neon ушёл в sleep и закрыл соединение) — заменяем его
    if conn.closed:
        pool.putconn(conn, close=True)
        conn = pool.getconn()
    return DBConnection(conn, pool)
