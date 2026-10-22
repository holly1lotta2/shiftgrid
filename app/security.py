"""Сессия, CSRF-защита и декораторы доступа."""
import secrets
from functools import wraps

from flask import abort, flash, g, redirect, request, session, url_for

from .db import complete_finished_shifts, get_db

CURRENT_USER_SQL = (
    "SELECT id, username, full_name, role, position, phone, created_at FROM users WHERE id = ?"
)


def get_csrf_token():
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_hex(16)
    return session["_csrf_token"]


def is_safe_next(target):
    """Разрешаем редирект только на относительный путь этого же сайта."""
    return (bool(target) and target.startswith("/")
            and not target.startswith("//") and "\\" not in target)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            flash("Войдите в систему, чтобы продолжить.", "warning")
            next_url = request.full_path.rstrip("?") if request.method == "GET" else None
            return redirect(url_for("auth.login", next=next_url))
        return view(*args, **kwargs)
    return wrapped


def role_required(role):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if g.user["role"] != role:
                abort(403)
            return view(*args, **kwargs)
        return login_required(wrapped)
    return decorator


def init_app(app):
    @app.before_request
    def load_current_user():
        g.user = None
        if request.endpoint == "static":
            return
        user_id = session.get("user_id")
        if user_id is None:
            return
        db = get_db()
        g.user = db.execute(CURRENT_USER_SQL, (user_id,)).fetchone()
        if g.user is None:
            session.clear()
            return
        complete_finished_shifts(db)

    @app.before_request
    def csrf_protect():
        if request.method != "POST":
            return
        expected = session.get("_csrf_token")
        received = request.form.get("csrf_token", "")
        if not expected or not secrets.compare_digest(expected, received):
            abort(400)
