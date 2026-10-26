"""SQLite: подключение, схема и демо-данные."""
import sqlite3
from datetime import date, datetime, timedelta

from flask import current_app, g
from werkzeug.security import generate_password_hash

from .constants import ACTIVE_REQUEST_STATUSES
from .timeutils import shift_bounds, week_start

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    full_name     TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('manager', 'employee')),
    position      TEXT NOT NULL DEFAULT '',
    phone         TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS shifts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    date       TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time   TEXT NOT NULL,
    position   TEXT NOT NULL,
    status     TEXT NOT NULL DEFAULT 'planned'
               CHECK (status IN ('planned', 'completed', 'cancelled')),
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_shifts_date ON shifts(date);
CREATE INDEX IF NOT EXISTS idx_shifts_user_date ON shifts(user_id, date);

CREATE TABLE IF NOT EXISTS swap_requests (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    shift_id     INTEGER NOT NULL REFERENCES shifts(id) ON DELETE CASCADE,
    from_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    to_user_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    reason       TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'pending_colleague'
                 CHECK (status IN ('pending_colleague', 'pending_manager', 'approved',
                                   'rejected', 'declined', 'cancelled')),
    created_at   TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at   TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_swap_requests_status ON swap_requests(status);
"""

DEMO_USERS = (
    # логин, пароль, имя, роль, должность, телефон
    ("manager", "manager123", "Лена Головач", "manager", "Управляющий", "+7 900 100-00-01"),
    ("ivan", "123456", "Гена Цидармян", "employee", "Бариста", "+7 900 100-00-02"),
    ("maria", "123456", "Матвей Подержика", "employee", "Кассир", "+7 900 100-00-03"),
    ("peter", "123456", "Рекорд Надоев", "employee", "Официант", "+7 900 100-00-04"),
    ("olga", "123456", "Запивон Закусович", "employee", "Повар", "+7 900 100-00-05"),
)

# Недельный график для демо: день недели (0 = Пн), начало, конец.
# У Марии смены по 12 часов — в отчёте за месяц у неё будет переработка.
DEMO_WEEK_PATTERN = {
    "ivan": ((0, "09:00", "17:00"), (1, "09:00", "17:00"), (2, "09:00", "17:00"), (4, "09:00", "17:00")),
    "maria": ((0, "10:00", "22:00"), (2, "10:00", "22:00"), (3, "10:00", "22:00"), (5, "10:00", "22:00")),
    "peter": ((1, "14:00", "23:00"), (3, "14:00", "23:00"), (4, "14:00", "23:00"), (5, "14:00", "23:00")),
    "olga": ((2, "12:00", "20:00"), (4, "22:00", "06:00"), (5, "22:00", "06:00"), (6, "22:00", "06:00")),
}

ACTIVE_PLACEHOLDERS = ", ".join("?" for _ in ACTIVE_REQUEST_STATUSES)


def connect(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_db():
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE"])
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_app(app):
    """Создаёт таблицы и при пустой базе заполняет её демо-данными."""
    app.teardown_appcontext(close_db)
    conn = connect(app.config["DATABASE"])
    try:
        conn.executescript(SCHEMA)
        if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
            seed_demo(conn)
        conn.commit()
    finally:
        conn.close()


def seed_demo(conn):
    """Команда из 5 человек, смены с начала месяца до конца следующей недели, 2 замены."""
    today = date.today()
    user_ids = {}
    for username, password, full_name, role, position, phone in DEMO_USERS:
        cur = conn.execute(
            "INSERT INTO users (username, password_hash, full_name, role, position, phone) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (username, generate_password_hash(password), full_name, role, position, phone),
        )
        user_ids[username] = cur.lastrowid

    positions = {user[0]: user[4] for user in DEMO_USERS}
    now = datetime.now()
    day = today.replace(day=1)
    last_day = week_start(today) + timedelta(days=13)
    while day <= last_day:
        for username, pattern in DEMO_WEEK_PATTERN.items():
            for weekday, start, end in pattern:
                if weekday != day.weekday():
                    continue
                status = "completed" if shift_bounds(day, start, end)[1] <= now else "planned"
                conn.execute(
                    "INSERT INTO shifts (user_id, date, start_time, end_time, position, status, created_by) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (user_ids[username], day.isoformat(), start, end, positions[username], status,
                     user_ids["manager"]),
                )
        day += timedelta(days=1)

    # Обе замены — на следующую неделю, поэтому они всегда в будущем.
    next_monday = week_start(today) + timedelta(days=7)
    demo_requests = (
        ("ivan", "peter", next_monday, "pending_colleague", "Экзамен в университете, подмени, пожалуйста."),
        ("maria", "olga", next_monday + timedelta(days=3), "pending_manager", "Семейные обстоятельства."),
    )
    for from_user, to_user, shift_day, status, reason in demo_requests:
        shift = conn.execute(
            "SELECT id FROM shifts WHERE user_id = ? AND date = ?",
            (user_ids[from_user], shift_day.isoformat()),
        ).fetchone()
        conn.execute(
            "INSERT INTO swap_requests (shift_id, from_user_id, to_user_id, reason, status) "
            "VALUES (?, ?, ?, ?, ?)",
            (shift["id"], user_ids[from_user], user_ids[to_user], reason, status),
        )


def reset_demo(db):
    """Стирает все данные и заново создаёт демо-команду с датами относительно сегодня."""
    with db:
        db.execute("DELETE FROM swap_requests")
        db.execute("DELETE FROM shifts")
        db.execute("DELETE FROM users")
        db.execute("DELETE FROM sqlite_sequence")
        seed_demo(db)


def clear_all_except(db, user_id):
    """Оставляет только указанного пользователя — чтобы начать вести свою команду."""
    with db:
        db.execute("DELETE FROM swap_requests")
        db.execute("DELETE FROM shifts")
        db.execute("DELETE FROM users WHERE id != ?", (user_id,))


def complete_finished_shifts(db):
    """Закончившиеся смены автоматически становятся «Отработана», их замены закрываются."""
    now = datetime.now()
    rows = db.execute(
        "SELECT id, date, start_time, end_time FROM shifts WHERE status = 'planned' AND date <= ?",
        (now.date().isoformat(),),
    ).fetchall()
    finished = [(row["id"],) for row in rows
                if shift_bounds(row["date"], row["start_time"], row["end_time"])[1] <= now]
    if not finished:
        return
    with db:
        db.executemany("UPDATE shifts SET status = 'completed' WHERE id = ?", finished)
        db.executemany(
            "UPDATE swap_requests SET status = 'cancelled', updated_at = datetime('now', 'localtime') "
            f"WHERE shift_id = ? AND status IN ({ACTIVE_PLACEHOLDERS})",
            [(shift_id, *ACTIVE_REQUEST_STATUSES) for (shift_id,) in finished],
        )
