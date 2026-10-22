"""Фильтры шаблонов, общий контекст и страницы ошибок."""
from datetime import date, datetime

from flask import current_app, g, render_template

from . import constants
from .db import get_db
from .security import get_csrf_token
from .timeutils import relative_day, ru_date


def ru_datetime(value):
    try:
        return datetime.strptime(str(value), "%Y-%m-%d %H:%M:%S").strftime("%d.%m.%Y %H:%M")
    except ValueError:
        return value


def hours_filter(value):
    """8.0 -> '8', 7.5 -> '7,5'."""
    text = f"{round(float(value or 0), 1):.1f}"
    if text.endswith(".0"):
        text = text[:-2]
    return text.replace(".", ",")


def nav_badge():
    """Число запросов, которые ждут действия текущего пользователя."""
    user = g.get("user")
    if user is None:
        return 0
    db = get_db()
    if user["role"] == "manager":
        sql, params = "SELECT COUNT(*) FROM swap_requests WHERE status = 'pending_manager'", ()
    else:
        sql = ("SELECT COUNT(*) FROM swap_requests "
               "WHERE status = 'pending_colleague' AND to_user_id = ?")
        params = (user["id"],)
    return db.execute(sql, params).fetchone()[0]


def init_app(app):
    app.add_template_filter(ru_date, "ru_date")
    app.add_template_filter(relative_day, "relative_day")
    app.add_template_filter(ru_datetime, "ru_datetime")
    app.add_template_filter(hours_filter, "hours")

    @app.context_processor
    def inject_globals():
        return {
            "csrf_token": get_csrf_token,
            "ROLES": constants.ROLES,
            "SHIFT_STATUSES": constants.SHIFT_STATUSES,
            "REQUEST_STATUSES": constants.REQUEST_STATUSES,
            "POSITIONS": constants.POSITIONS,
            "NORM_HOURS": constants.MONTHLY_NORM_HOURS,
            "MIN_PASSWORD_LENGTH": constants.MIN_PASSWORD_LENGTH,
            "PUBLIC_MODE": current_app.config["PUBLIC_MODE"],
            "nav_badge": nav_badge(),
            "today": date.today(),
        }

    def render_error(code, title, message):
        return render_template("error.html", code=code, title=title, message=message), code

    @app.errorhandler(400)
    def bad_request(_error):
        return render_error(400, "Некорректный запрос",
                            "Форма устарела. Обновите страницу и попробуйте ещё раз.")

    @app.errorhandler(403)
    def forbidden(_error):
        return render_error(403, "Нет доступа", "Эта страница недоступна для вашей роли.")

    @app.errorhandler(404)
    def not_found(_error):
        return render_error(404, "Страница не найдена", "Такой страницы или записи не существует.")

    @app.errorhandler(405)
    def method_not_allowed(_error):
        return render_error(405, "Действие недоступно", "Откройте страницу через меню приложения.")
