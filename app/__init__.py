"""ShiftGrid — планирование смен для Horeca и ритейла."""
import os
import secrets

from flask import Flask


def create_app(overrides=None):
    """overrides — настройки поверх стандартных (PUBLIC_MODE, DATABASE для тестов и т.п.)."""
    app = Flask(__name__, instance_relative_config=True)
    os.makedirs(app.instance_path, exist_ok=True)
    app.config.update(
        DATABASE=os.path.join(app.instance_path, "shiftgrid.db"),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        # Публичный режим: сайт открыт по ссылке из интернета, массовое удаление данных отключено.
        PUBLIC_MODE=False,
    )
    if overrides:
        app.config.update(overrides)
    if not app.config.get("SECRET_KEY"):
        app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or load_secret_key(app.instance_path)

    from . import compression, db, filters, security
    from .views import account, auth, dashboard, schedule, shifts, staff, swaps

    db.init_app(app)
    security.init_app(app)
    filters.init_app(app)
    compression.init_app(app)
    for module in (auth, dashboard, schedule, shifts, staff, swaps, account):
        app.register_blueprint(module.bp)
    return app


def load_secret_key(instance_path):
    """Ключ сессий хранится в instance/, чтобы вход не сбрасывался после перезапуска."""
    path = os.path.join(instance_path, "secret_key")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            key = fh.read().strip()
        if key:
            return key
    key = secrets.token_hex(32)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(key)
    return key
