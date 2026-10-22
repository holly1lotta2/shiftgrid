"""Пользователи: выборки, проверка полей, создание сотрудников."""
import re
import sqlite3

from werkzeug.security import generate_password_hash

from ..constants import (
    MAX_NAME_LENGTH,
    MAX_PASSWORD_LENGTH,
    MAX_PHONE_LENGTH,
    MAX_POSITION_LENGTH,
    MIN_PASSWORD_LENGTH,
)

USERNAME_RE = re.compile(r"^[a-z0-9_.-]{3,30}$")
PHONE_RE = re.compile(r"^[0-9+()\- ]{5,30}$")
EMPLOYEE_COLUMNS = "id, username, full_name, position, phone, created_at"


def list_employees(db):
    return db.execute(
        f"SELECT {EMPLOYEE_COLUMNS} FROM users WHERE role = 'employee' ORDER BY full_name"
    ).fetchall()


def get_employee(db, user_id):
    return db.execute(
        f"SELECT {EMPLOYEE_COLUMNS} FROM users WHERE id = ? AND role = 'employee'", (user_id,)
    ).fetchone()


def colleagues_of(db, user_id):
    return db.execute(
        f"SELECT {EMPLOYEE_COLUMNS} FROM users WHERE role = 'employee' AND id != ? ORDER BY full_name",
        (user_id,),
    ).fetchall()


def read_profile(form):
    return {
        "full_name": form.get("full_name", "").strip(),
        "position": form.get("position", "").strip(),
        "phone": form.get("phone", "").strip(),
    }


def validate_profile(profile):
    errors = []
    if not 2 <= len(profile["full_name"]) <= MAX_NAME_LENGTH:
        errors.append(f"Имя: от 2 до {MAX_NAME_LENGTH} символов.")
    if len(profile["position"]) > MAX_POSITION_LENGTH:
        errors.append(f"Должность: не длиннее {MAX_POSITION_LENGTH} символов.")
    if profile["phone"] and (len(profile["phone"]) > MAX_PHONE_LENGTH
                             or not PHONE_RE.match(profile["phone"])):
        errors.append("Телефон: только цифры, пробелы и символы + - ( ).")
    return errors


def validate_username(db, username):
    if not USERNAME_RE.match(username):
        return "Логин: 3–30 символов — латинские буквы, цифры, точка, дефис, подчёркивание."
    if db.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
        return "Такой логин уже занят."
    return None


def validate_password(password, confirm=None):
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Пароль должен быть не короче {MIN_PASSWORD_LENGTH} символов."
    if len(password) > MAX_PASSWORD_LENGTH:
        return f"Пароль должен быть не длиннее {MAX_PASSWORD_LENGTH} символов."
    if confirm is not None and password != confirm:
        return "Пароли не совпадают."
    return None


def create_employee(db, username, password, profile):
    """Возвращает False, если логин успели занять между проверкой и вставкой."""
    try:
        with db:
            db.execute(
                "INSERT INTO users (username, password_hash, full_name, role, position, phone) "
                "VALUES (?, ?, ?, 'employee', ?, ?)",
                (username, generate_password_hash(password), profile["full_name"],
                 profile["position"], profile["phone"]),
            )
    except sqlite3.IntegrityError:
        return False
    return True


def set_password(db, user_id, password):
    with db:
        db.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                   (generate_password_hash(password), user_id))
