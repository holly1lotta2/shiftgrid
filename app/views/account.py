"""Профиль, смена пароля и управление данными (сброс демо, чистый старт)."""
from datetime import date
from functools import wraps

from flask import Blueprint, current_app, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from ..constants import RU_MONTHS
from ..db import clear_all_except, get_db, reset_demo
from ..logic import reports
from ..logic.users import read_profile, set_password, validate_password, validate_profile
from ..security import login_required, role_required
from ..timeutils import overtime_of
from . import flash_errors

bp = Blueprint("account", __name__)
CLEAR_CONFIRM_WORD = "УДАЛИТЬ"


def local_mode_only(what):
    """Действие недоступно, когда сайт открыт по публичной ссылке (что угодно может нажать любой)."""
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if current_app.config["PUBLIC_MODE"]:
                flash(f"Пока сайт открыт по публичной ссылке, {what} отключено. "
                      "Запустите start.bat, чтобы сделать это.", "warning")
                return redirect(url_for("account.profile"))
            return view(*args, **kwargs)
        return wrapped
    return decorator


@bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    db = get_db()
    user_id = g.user["id"]
    if request.method == "POST":
        data = read_profile(request.form)
        data["position"] = g.user["position"]  # должность назначает управляющий
        errors = validate_profile(data)
        if errors:
            flash_errors(errors)
        else:
            with db:
                db.execute("UPDATE users SET full_name = ?, phone = ? WHERE id = ?",
                           (data["full_name"], data["phone"], user_id))
            flash("Профиль сохранён.", "success")
        return redirect(url_for("account.profile"))

    today = date.today()
    if g.user["role"] == "manager":
        stats = {
            "employees": db.execute("SELECT COUNT(*) FROM users WHERE role = 'employee'").fetchone()[0],
            "shifts": db.execute("SELECT COUNT(*) FROM shifts").fetchone()[0],
        }
    else:
        month_hours = reports.user_month_hours(db, user_id, today.year, today.month)
        stats = {
            "shifts": db.execute(
                "SELECT COUNT(*) FROM shifts WHERE user_id = ? AND status != 'cancelled'", (user_id,)
            ).fetchone()[0],
            "month_hours": month_hours,
            "overtime": overtime_of(month_hours),
        }
    return render_template("account/profile.html", stats=stats, month_name=RU_MONTHS[today.month],
                           confirm_word=CLEAR_CONFIRM_WORD)


@bp.route("/profile/password", methods=["POST"])
@login_required
@local_mode_only("изменение пароля")
def password():
    db = get_db()
    stored = db.execute("SELECT password_hash FROM users WHERE id = ?", (g.user["id"],)).fetchone()
    if not check_password_hash(stored["password_hash"], request.form.get("current_password", "")):
        flash("Текущий пароль указан неверно.", "danger")
        return redirect(url_for("account.profile"))
    new_password = request.form.get("new_password", "")
    error = validate_password(new_password, request.form.get("new_password_confirm", ""))
    if error:
        flash(error, "danger")
    else:
        set_password(db, g.user["id"], new_password)
        flash("Пароль изменён.", "success")
    return redirect(url_for("account.profile"))


@bp.route("/settings/reset-demo", methods=["POST"])
@role_required("manager")
@local_mode_only("восстановление демо-данных")
def reset_demo_data():
    reset_demo(get_db())
    session.clear()
    flash("Демо-данные восстановлены с датами от сегодняшнего дня. Войдите снова.", "success")
    return redirect(url_for("auth.login"))


@bp.route("/settings/clear", methods=["POST"])
@role_required("manager")
@local_mode_only("удаление данных")
def clear_data():
    if request.form.get("confirm", "").strip().upper() != CLEAR_CONFIRM_WORD:
        flash(f"Для подтверждения введите слово {CLEAR_CONFIRM_WORD}.", "danger")
        return redirect(url_for("account.profile"))
    clear_all_except(get_db(), g.user["id"])
    flash("Все сотрудники, смены и замены удалены. Добавьте свою команду.", "success")
    return redirect(url_for("staff.employees"))
