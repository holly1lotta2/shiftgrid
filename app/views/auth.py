"""Вход и выход."""
from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from ..db import DEMO_USERS, get_db
from ..security import is_safe_next

bp = Blueprint("auth", __name__)


def demo_accounts(db):
    """Демо-аккаунты, которые ещё есть в базе, — для входа в один клик."""
    usernames = [user[0] for user in DEMO_USERS]
    placeholders = ", ".join("?" for _ in usernames)
    rows = db.execute(
        f"SELECT username, full_name, role, position FROM users WHERE username IN ({placeholders})",
        usernames,
    ).fetchall()
    found = {row["username"]: row for row in rows}
    return [
        {**dict(found[username]), "password": password}
        for username, password, *_ in DEMO_USERS
        if username in found
    ]


@bp.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(url_for("dashboard.home"))
    db = get_db()
    next_url = request.values.get("next", "")
    username = ""
    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")
        user = db.execute(
            "SELECT id, full_name, password_hash FROM users WHERE username = ?", (username,)
        ).fetchone()
        if user is not None and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            flash(f"Добро пожаловать, {user['full_name']}!", "success")
            return redirect(next_url if is_safe_next(next_url) else url_for("dashboard.home"))
        flash("Неверный логин или пароль.", "danger")
        return render_template("auth/login.html", username=username, next_url=next_url,
                               demo_accounts=demo_accounts(db)), 401
    return render_template("auth/login.html", username=username, next_url=next_url,
                           demo_accounts=demo_accounts(db))


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("Вы вышли из системы.", "info")
    return redirect(url_for("auth.login"))
