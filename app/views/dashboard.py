"""Главная страница: сводка для управляющего и для сотрудника."""
from datetime import date, datetime, timedelta

from flask import Blueprint, g, redirect, render_template, url_for

from ..constants import DASHBOARD_REQUESTS_LIMIT, RU_MONTHS, RU_MONTHS_GENITIVE, UPCOMING_SHIFTS_LIMIT
from ..db import get_db
from ..logic import reports, shifts, swaps
from ..logic.coverage import coverage_strip, day_coverage
from ..security import login_required
from ..timeutils import norm_percent, overtime_of, to_hours, week_start

bp = Blueprint("dashboard", __name__)


@bp.route("/")
def index():
    return redirect(url_for("dashboard.home" if g.user else "auth.login"))


@bp.route("/dashboard")
@login_required
def home():
    if g.user["role"] == "manager":
        return manager_dashboard()
    return employee_dashboard()


def manager_dashboard():
    db = get_db()
    today = date.today()
    monday = week_start(today)
    week = shifts.shifts_between(db, monday, monday + timedelta(days=6))
    active_week = [s for s in week if s["status"] != "cancelled"]
    around_today = shifts.shifts_between(db, today - timedelta(days=1), today)
    now = datetime.now()
    report = reports.month_report(db, today.year, today.month)
    waiting = swaps.list_requests(db, "r.status = 'pending_manager'", limit=DASHBOARD_REQUESTS_LIMIT)
    stats = {
        "employees": len(report),
        "week_shifts": len(active_week),
        "week_hours": to_hours(sum(s["minutes"] for s in active_week)),
        "pending": db.execute(
            "SELECT COUNT(*) FROM swap_requests WHERE status = 'pending_manager'"
        ).fetchone()[0],
    }
    return render_template(
        "dashboard/manager.html",
        stats=stats,
        today_shifts=[s for s in week if s["date"] == today.isoformat()],
        today_coverage=coverage_strip(around_today, today, max(day_coverage(around_today, today))),
        now_percent=round((now.hour * 60 + now.minute) / (24 * 60) * 100, 1),
        now_count=sum(1 for s in around_today if s["is_now"]),
        waiting=waiting,
        overtime=[row for row in report if row["overtime"] > 0],
        team_hours=round(sum(row["hours"] for row in report), 2),
        month_name=RU_MONTHS[today.month],
        month_genitive=RU_MONTHS_GENITIVE[today.month],
        week_start=monday,
        week_end=monday + timedelta(days=6),
    )


def employee_dashboard():
    db = get_db()
    user_id = g.user["id"]
    today = date.today()
    upcoming = shifts.upcoming_shifts(db, user_id, UPCOMING_SHIFTS_LIMIT)
    outgoing_active = swaps.list_requests(
        db, "r.from_user_id = ? AND r.status IN ('pending_colleague', 'pending_manager')", (user_id,)
    )
    planned = reports.user_month_hours(db, user_id, today.year, today.month)
    return render_template(
        "dashboard/employee.html",
        next_shift=upcoming[0] if upcoming else None,
        upcoming=upcoming[1:],
        swap_shift_ids={item["shift_id"] for item in outgoing_active},
        worked_hours=reports.user_month_hours(db, user_id, today.year, today.month, ("completed",)),
        planned_hours=planned,
        overtime=overtime_of(planned),
        percent=norm_percent(planned),
        incoming=swaps.list_requests(
            db, "r.to_user_id = ? AND r.status = 'pending_colleague'", (user_id,)
        ),
        month_name=RU_MONTHS[today.month],
    )
