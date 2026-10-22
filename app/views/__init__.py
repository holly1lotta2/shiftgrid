"""Страницы приложения (Flask blueprints)."""
from flask import flash


def flash_errors(errors):
    for error in errors:
        flash(error, "danger")
