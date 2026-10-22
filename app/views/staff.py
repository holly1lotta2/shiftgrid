"""Сотрудники (для управляющего) и коллеги (для сотрудника)."""
from datetime import date

from flask import Blueprint, Response, abort, current_app, flash, g, redirect, render_template, request, url_for

from ..constants import RU_MONTHS
from ..db import get_db
from ..logic import reports
from ..logic.users import (
    colleagues_of,
    create_employee,
    get_employee,
    read_profile,
    set_password,
    validate_password,
    validate_profile,
    validate_username,
)
from ..security import role_required
from ..timeutils import add_months
from . import flash_errors

bp = Blueprint("staff", __name__)


def month_args():
    today = date.today()
    year = request.args.get("year", type=int) or today.year
    month = request.args.get("month", type=int) or today.month
    if not (2000 <= year <= 2100 and 1 <= month <= 12):
        return today.year, today.month
    return year, month


def render_employees(form, status=200):
    year, month = month_args()
    prev_year, prev_month = add_months(year, month, -1)
    next_year, next_month = add_months(year, month, 1)
    return render_template(
        "staff/employees.html",
        report=reports.month_report(get_db(), year, month),
        form=form,
        year=year,
        month=month,
        month_name=RU_MONTHS[month],
        prev_period={"year": prev_year, "month": prev_month},
        next_period={"year": next_year, "month": next_month},
    ), status


@bp.route("/employees")
@role_required("manager")
def employees():
    return render_employees(form={})


@bp.route("/employees", methods=["POST"])
@role_required("manager")
def create():
    db = get_db()
    username = request.form.get("username", "").strip().lower()
    password = request.form.get("password", "")
    profile = read_profile(request.form)
    errors = validate_profile(profile)
    errors += [e for e in (validate_username(db, username), validate_password(password)) if e]
    if not errors and not create_employee(db, username, password, profile):
        errors.append("Такой логин уже занят.")
    if errors:
        flash_errors(errors)
        return render_employees(request.form, 400)
    flash(f"Сотрудник {profile['full_name']} добавлен. Логин: {username}.", "success")
    return redirect(url_for("staff.employees"))


@bp.route("/employees/<int:user_id>/edit", methods=["GET", "POST"])
@role_required("manager")
def edit(user_id):
    db = get_db()
    employee = get_employee(db, user_id) or abort(404)
    if request.method == "POST":
        profile = read_profile(request.form)
        new_password = request.form.get("new_password", "")
        errors = validate_profile(profile)
        if new_password and current_app.config["PUBLIC_MODE"]:
            errors.append("Пока сайт открыт по публичной ссылке, пароли менять нельзя.")
        elif new_password:
            errors += [e for e in (validate_password(new_password),) if e]
        if errors:
            flash_errors(errors)
            return render_template("staff/employee_form.html", employee=employee,
                                   form=request.form), 400
        with db:
            db.execute("UPDATE users SET full_name = ?, position = ?, phone = ? WHERE id = ?",
                       (profile["full_name"], profile["position"], profile["phone"], user_id))
        if new_password:
            set_password(db, user_id, new_password)
        flash("Данные сотрудника сохранены." + (" Пароль изменён." if new_password else ""), "success")
        return redirect(url_for("staff.employees"))
    return render_template("staff/employee_form.html", employee=employee, form=dict(employee))


@bp.route("/employees/<int:user_id>/delete", methods=["POST"])
@role_required("manager")
def delete(user_id):
    db = get_db()
    employee = get_employee(db, user_id)
    if employee is None:
        flash("Сотрудник не найден.", "danger")
        return redirect(url_for("staff.employees"))
    with db:
        db.execute("DELETE FROM users WHERE id = ?", (user_id,))
    flash(f"Сотрудник {employee['full_name']} удалён вместе с его сменами и заменами.", "success")
    return redirect(url_for("staff.employees"))


@bp.route("/employees/report.csv")
@role_required("manager")
def report_csv():
    year, month = month_args()
    body = reports.report_csv(reports.month_report(get_db(), year, month))
    return Response(
        body,
        content_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="shiftgrid-hours-{year}-{month:02d}.csv"'},
    )


@bp.route("/colleagues")
@role_required("employee")
def colleagues():
    return render_template("staff/colleagues.html", colleagues=colleagues_of(get_db(), g.user["id"]))
