"""Часы и переработки: по сотруднику, по команде, выгрузка в CSV."""
import csv
import io

from ..constants import MONTHLY_NORM_HOURS
from ..timeutils import duration_minutes, month_range, norm_percent, overtime_of, to_hours
from .users import list_employees

# В часы идут запланированные и отработанные смены; отменённые — нет.
COUNTED_STATUSES = ("planned", "completed")
COUNTED_PLACEHOLDERS = ", ".join("?" for _ in COUNTED_STATUSES)


def user_month_hours(db, user_id, year, month, statuses=COUNTED_STATUSES):
    """Часы сотрудника за месяц. Ночная смена целиком относится к дню начала."""
    first, last = month_range(year, month)
    placeholders = ", ".join("?" for _ in statuses)
    rows = db.execute(
        "SELECT start_time, end_time FROM shifts "
        f"WHERE user_id = ? AND date BETWEEN ? AND ? AND status IN ({placeholders})",
        (user_id, first.isoformat(), last.isoformat(), *statuses),
    ).fetchall()
    return to_hours(sum(duration_minutes(r["start_time"], r["end_time"]) for r in rows))


def month_report(db, year, month):
    """Строка отчёта на каждого сотрудника — одним запросом по сменам месяца."""
    first, last = month_range(year, month)
    rows = db.execute(
        "SELECT user_id, start_time, end_time FROM shifts "
        f"WHERE date BETWEEN ? AND ? AND status IN ({COUNTED_PLACEHOLDERS})",
        (first.isoformat(), last.isoformat(), *COUNTED_STATUSES),
    ).fetchall()
    minutes, counts = {}, {}
    for row in rows:
        uid = row["user_id"]
        minutes[uid] = minutes.get(uid, 0) + duration_minutes(row["start_time"], row["end_time"])
        counts[uid] = counts.get(uid, 0) + 1

    report = []
    for emp in list_employees(db):
        hours = to_hours(minutes.get(emp["id"], 0))
        report.append({
            "id": emp["id"],
            "username": emp["username"],
            "full_name": emp["full_name"],
            "position": emp["position"],
            "phone": emp["phone"],
            "shift_count": counts.get(emp["id"], 0),
            "hours": hours,
            "overtime": overtime_of(hours),
            "percent": norm_percent(hours),
        })
    return report


def hours_by_user(shifts):
    """{user_id: часы} по уже выбранным сменам (отменённые не считаются)."""
    minutes = {}
    for shift in shifts:
        if shift["status"] != "cancelled":
            minutes[shift["user_id"]] = minutes.get(shift["user_id"], 0) + shift["minutes"]
    return {uid: to_hours(value) for uid, value in minutes.items()}


def report_csv(report):
    """CSV для Excel: разделитель «;», UTF-8 с BOM, запятая в дробях."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow(["Сотрудник", "Логин", "Должность", "Смен", "Часы", "Норма", "Переработка"])
    for row in report:
        writer.writerow([
            row["full_name"], row["username"], row["position"], row["shift_count"],
            str(row["hours"]).replace(".", ","), MONTHLY_NORM_HOURS,
            str(row["overtime"]).replace(".", ","),
        ])
    return "﻿" + buffer.getvalue()
