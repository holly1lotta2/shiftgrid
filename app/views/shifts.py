"""Создание, редактирование и удаление смен (только управляющий)."""
from datetime import date

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from ..db import get_db
from ..logic.shifts import (
    close_active_requests,
    get_shift,
    insert_shift,
    validate_shift_form,
)
from ..logic.users import get_employee, list_employees
from ..security import role_required
from ..timeutils import is_overnight, parse_date, ru_date
from . import flash_errors

bp = Blueprint("shifts", __name__, url_prefix="/shifts")


def week_redirect(day):
    return redirect(url_for("schedule.view", view="week", date=day))


def render_form(shift, form, status=200):
    employees = list_employees(get_db())
    return render_template("shifts/form.html", shift=shift, employees=employees, form=form), status


@bp.route("/new", methods=["GET", "POST"])
@role_required("manager")
def new():
    db = get_db()
    if request.method == "POST":
        data, errors = validate_shift_form(db, request.form)
        if errors:
            flash_errors(errors)
            return render_form(None, request.form, 400)
        with db:
            insert_shift(db, data, g.user["id"])
        flash(f"Смена добавлена: {ru_date(data['date'])}, {data['start_time']}–{data['end_time']}.",
              "success")
        if request.form.get("add_another") == "1":
            return redirect(url_for("shifts.new", date=data["date"]))
        return week_redirect(data["date"])

    employee = get_employee(db, request.args.get("user_id", type=int) or 0)
    form = {
        "user_id": str(employee["id"]) if employee else "",
        "date": (parse_date(request.args.get("date")) or date.today()).isoformat(),
        "start_time": "09:00",
        "end_time": "17:00",
        "position": employee["position"] if employee else "",
    }
    return render_form(None, form)


@bp.route("/<int:shift_id>/edit", methods=["GET", "POST"])
@role_required("manager")
def edit(shift_id):
    db = get_db()
    shift = get_shift(db, shift_id) or abort(404)
    if request.method == "POST":
        data, errors = validate_shift_form(db, request.form, exclude_id=shift_id)
        if errors:
            flash_errors(errors)
            return render_form(shift, request.form, 400)
        with db:
            db.execute(
                "UPDATE shifts SET user_id = ?, date = ?, start_time = ?, end_time = ?, "
                "position = ?, status = ? WHERE id = ?",
                (data["user_id"], data["date"], data["start_time"], data["end_time"],
                 data["position"], data["status"], shift_id),
            )
            if data["user_id"] != shift["user_id"] or data["status"] != "planned":
                # Смена ушла другому или больше не запланирована — замены по ней неактуальны.
                close_active_requests(db, shift_id, "cancelled")
        flash("Смена сохранена.", "success")
        return week_redirect(data["date"])

    form = {
        "user_id": str(shift["user_id"]),
        "date": shift["date"],
        "start_time": shift["start_time"],
        "end_time": shift["end_time"],
        "position": shift["position"],
        "status": shift["status"],
        "overnight": "1" if is_overnight(shift["start_time"], shift["end_time"]) else "",
    }
    return render_form(shift, form)


@bp.route("/<int:shift_id>/delete", methods=["POST"])
@role_required("manager")
def delete(shift_id):
    db = get_db()
    shift = get_shift(db, shift_id) or abort(404)
    with db:
        db.execute("DELETE FROM shifts WHERE id = ?", (shift_id,))
    flash("Смена удалена.", "success")
    return week_redirect(shift["date"])
