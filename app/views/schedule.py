"""График смен: неделя (основной вид для планирования) и месяц."""
import calendar
from datetime import date, timedelta

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from ..constants import RU_MONTHS, RU_WEEKDAYS_SHORT
from ..db import get_db
from ..logic import reports, shifts
from ..logic.coverage import week_strips
from ..logic.users import list_employees
from ..security import login_required, role_required
from ..timeutils import (
    add_months,
    overtime_of,
    parse_date,
    to_hours,
    week_label,
    week_start,
)

bp = Blueprint("schedule", __name__)
VIEW_MODES = ("week", "month")


def schedule_url(view_mode, anchor, employee=None):
    args = {"view": view_mode, "date": anchor.isoformat()}
    if employee:
        args["employee"] = employee
    return url_for("schedule.view", **args)


@bp.route("/schedule")
@login_required
def view():
    db = get_db()
    today = date.today()
    is_manager = g.user["role"] == "manager"
    view_mode = request.args.get("view", "week")
    if view_mode not in VIEW_MODES:
        view_mode = "week"
    anchor = parse_date(request.args.get("date")) or today
    if not 2000 <= anchor.year <= 2100:
        anchor = today

    employees, selected = [], None
    if is_manager:
        employees = list_employees(db)
        selected = request.args.get("employee", type=int)
        if selected not in {emp["id"] for emp in employees}:
            selected = None
    # Сотрудник видит только свои смены — фильтр по user_id прямо в SQL.
    user_filter = selected if is_manager else g.user["id"]

    context = {
        "view_mode": view_mode,
        "is_manager": is_manager,
        "employees": employees,
        "selected": selected,
        "weekdays": RU_WEEKDAYS_SHORT,
        "week_url": schedule_url("week", anchor, selected),
        "month_url": schedule_url("month", anchor, selected),
    }
    if view_mode == "week":
        context.update(week_context(db, anchor, user_filter, selected, employees))
        return render_template("schedule/week.html", **context)
    context.update(month_context(db, anchor, user_filter, selected))
    return render_template("schedule/month.html", **context)


def week_context(db, anchor, user_filter, selected, employees):
    monday = week_start(anchor)
    days = [monday + timedelta(days=i) for i in range(7)]
    # Берём и воскресенье прошлой недели: его ночная смена заходит в понедельник.
    with_previous_night = shifts.shifts_between(db, monday - timedelta(days=1), days[-1], user_filter)
    week = [s for s in with_previous_night if s["date"] >= monday.isoformat()]

    grid, by_day = {}, {}
    day_totals = {day.isoformat(): {"count": 0, "minutes": 0} for day in days}
    for shift in week:
        grid.setdefault(f"{shift['user_id']}|{shift['date']}", []).append(shift)
        by_day.setdefault(shift["date"], []).append(shift)
        if shift["status"] != "cancelled":
            day_totals[shift["date"]]["count"] += 1
            day_totals[shift["date"]]["minutes"] += shift["minutes"]
    for totals in day_totals.values():
        totals["hours"] = to_hours(totals["minutes"])

    return {
        "days": days,
        "monday": monday,
        "grid": grid,
        "by_day": by_day,
        "rows": [emp for emp in employees if not selected or emp["id"] == selected],
        "day_totals": day_totals,
        "coverage": week_strips(with_previous_night, days),
        "week_hours": reports.hours_by_user(week),
        "total_hours": to_hours(sum(t["minutes"] for t in day_totals.values())),
        "period_label": week_label(monday),
        "prev_url": schedule_url("week", monday - timedelta(days=7), selected),
        "next_url": schedule_url("week", monday + timedelta(days=7), selected),
        "today_url": schedule_url("week", date.today(), selected),
        "can_copy": days[-1] >= date.today(),
    }


def month_context(db, anchor, user_filter, selected):
    year, month = anchor.year, anchor.month
    weeks = calendar.Calendar(firstweekday=0).monthdatescalendar(year, month)
    by_date = {}
    for shift in shifts.shifts_between(db, weeks[0][0], weeks[-1][-1], user_filter):
        by_date.setdefault(shift["date"], []).append(shift)

    month_hours = reports.user_month_hours(db, user_filter, year, month) if user_filter else None
    prev_year, prev_month = add_months(year, month, -1)
    next_year, next_month = add_months(year, month, 1)
    return {
        "weeks": weeks,
        "month": month,
        "by_date": by_date,
        "month_hours": month_hours,
        "month_overtime": overtime_of(month_hours) if month_hours is not None else 0,
        "period_label": f"{RU_MONTHS[month]} {year}",
        "prev_url": schedule_url("month", date(prev_year, prev_month, 1), selected),
        "next_url": schedule_url("month", date(next_year, next_month, 1), selected),
        "today_url": schedule_url("month", date.today(), selected),
    }


@bp.route("/schedule/copy-week", methods=["POST"])
@role_required("manager")
def copy_week():
    monday = parse_date(request.form.get("week"))
    if monday is None:
        abort(400)
    monday = week_start(monday)
    if monday + timedelta(days=6) < date.today():
        flash("Нельзя копировать смены в уже прошедшую неделю.", "danger")
        return redirect(schedule_url("week", monday))

    copied, skipped = shifts.copy_previous_week(get_db(), monday, g.user["id"])
    if copied == 0 and skipped == 0:
        flash("На прошлой неделе нет смен для копирования.", "info")
    else:
        message = f"Скопировано смен с прошлой недели: {copied}."
        if skipped:
            message += f" Пропущено из-за пересечений: {skipped}."
        flash(message, "success")
    return redirect(schedule_url("week", monday))
