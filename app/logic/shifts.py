"""Смены: выборки, проверка формы, пересечения, копирование недели."""
from datetime import date, datetime, timedelta

from ..constants import (
    ACTIVE_REQUEST_STATUSES,
    EMPLOYEE_COLORS,
    MAX_POSITION_LENGTH,
    MAX_SCHEDULE_DAYS,
    MAX_SHIFT_MINUTES,
    SHIFT_STATUSES,
)
from ..timeutils import (
    duration_minutes,
    is_overnight,
    normalize_time,
    parse_date,
    ru_date,
    shift_bounds,
    to_hours,
    to_minutes,
)

SHIFT_WITH_USER_SQL = "SELECT s.*, u.full_name FROM shifts s JOIN users u ON u.id = s.user_id"
ACTIVE_PLACEHOLDERS = ", ".join("?" for _ in ACTIVE_REQUEST_STATUSES)


def decorate(row, now=None):
    """Строка смены + вычисляемые поля для шаблонов."""
    now = now or datetime.now()
    shift = dict(row)
    start, end = shift_bounds(row["date"], row["start_time"], row["end_time"])
    minutes = duration_minutes(row["start_time"], row["end_time"])
    shift.update(
        minutes=minutes,
        hours=to_hours(minutes),
        overnight=is_overnight(row["start_time"], row["end_time"]),
        color=row["user_id"] % EMPLOYEE_COLORS,
        is_now=row["status"] != "cancelled" and start <= now < end,
        is_future=start > now,
    )
    return shift


def get_shift(db, shift_id):
    return db.execute("SELECT * FROM shifts WHERE id = ?", (shift_id,)).fetchone()


def shifts_between(db, first, last, user_id=None):
    sql = SHIFT_WITH_USER_SQL + " WHERE s.date BETWEEN ? AND ?"
    params = [first.isoformat(), last.isoformat()]
    if user_id:
        sql += " AND s.user_id = ?"
        params.append(user_id)
    sql += " ORDER BY s.date, s.start_time"
    now = datetime.now()
    return [decorate(row, now) for row in db.execute(sql, params).fetchall()]


def upcoming_shifts(db, user_id, limit):
    """Ближайшие неотменённые смены сотрудника, включая идущую прямо сейчас."""
    rows = db.execute(
        SHIFT_WITH_USER_SQL + " WHERE s.user_id = ? AND s.status = 'planned' AND s.date >= ? "
        "ORDER BY s.date, s.start_time",
        (user_id, (date.today() - timedelta(days=1)).isoformat()),
    ).fetchall()
    now = datetime.now()
    result = []
    for row in rows:
        if shift_bounds(row["date"], row["start_time"], row["end_time"])[1] > now:
            result.append(decorate(row, now))
        if len(result) == limit:
            break
    return result


def find_overlap(db, user_id, day, start_time, end_time, exclude_id=None):
    """Пересекающаяся смена сотрудника или None (ночные смены учитываются)."""
    new_start, new_end = shift_bounds(day, start_time, end_time)
    center = new_start.date()
    rows = db.execute(
        "SELECT id, date, start_time, end_time FROM shifts "
        "WHERE user_id = ? AND status != 'cancelled' AND id != ? AND date BETWEEN ? AND ?",
        (user_id, exclude_id or -1,
         (center - timedelta(days=1)).isoformat(), (center + timedelta(days=1)).isoformat()),
    ).fetchall()
    for row in rows:
        start, end = shift_bounds(row["date"], row["start_time"], row["end_time"])
        if start < new_end and new_start < end:
            return row
    return None


def _time_errors(start_time, end_time, overnight):
    if not start_time or not end_time:
        return ["Укажите время начала и окончания в формате ЧЧ:ММ."]
    start_min, end_min = to_minutes(start_time), to_minutes(end_time)
    if start_min == end_min:
        return ["Время начала и окончания совпадают."]
    if end_min < start_min and not overnight:
        return ["Окончание раньше начала. Если смена ночная — отметьте «Смена через полночь»."]
    if end_min > start_min and overnight:
        return ["Отмечено «Смена через полночь», но окончание позже начала."]
    if duration_minutes(start_time, end_time) > MAX_SHIFT_MINUTES:
        return [f"Смена не может длиться дольше {MAX_SHIFT_MINUTES // 60} часов."]
    return []


def validate_shift_form(db, form, exclude_id=None):
    """Возвращает (данные, ошибки)."""
    errors = []
    user_id = form.get("user_id", type=int)
    if not user_id or not db.execute(
        "SELECT 1 FROM users WHERE id = ? AND role = 'employee'", (user_id,)
    ).fetchone():
        errors.append("Выберите сотрудника.")

    shift_date = parse_date(form.get("date"))
    if shift_date is None:
        errors.append("Укажите дату смены.")
    elif abs((shift_date - date.today()).days) > MAX_SCHEDULE_DAYS:
        errors.append("Дата смены должна быть в пределах года от сегодняшнего дня.")

    start_time, end_time = normalize_time(form.get("start_time")), normalize_time(form.get("end_time"))
    errors.extend(_time_errors(start_time, end_time, form.get("overnight") == "1"))

    position = form.get("position", "").strip()
    if not position or len(position) > MAX_POSITION_LENGTH:
        errors.append(f"Укажите должность (до {MAX_POSITION_LENGTH} символов).")

    status = form.get("status") or "planned"
    if status not in SHIFT_STATUSES:
        errors.append("Некорректный статус смены.")

    if not errors and status != "cancelled":
        overlap = find_overlap(db, user_id, shift_date, start_time, end_time, exclude_id)
        if overlap:
            errors.append(
                f"У сотрудника уже есть смена {overlap['start_time']}–{overlap['end_time']} "
                f"({ru_date(overlap['date'])}), она пересекается с этой."
            )

    data = {
        "user_id": user_id,
        "date": shift_date.isoformat() if shift_date else None,
        "start_time": start_time,
        "end_time": end_time,
        "position": position,
        "status": status,
    }
    return data, errors


def insert_shift(db, data, created_by, status="planned"):
    db.execute(
        "INSERT INTO shifts (user_id, date, start_time, end_time, position, status, created_by) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (data["user_id"], data["date"], data["start_time"], data["end_time"],
         data["position"], status, created_by),
    )


def close_active_requests(db, shift_id, status):
    """Закрывает незавершённые замены по смене (например, если смену отменили)."""
    db.execute(
        "UPDATE swap_requests SET status = ?, updated_at = datetime('now', 'localtime') "
        f"WHERE shift_id = ? AND status IN ({ACTIVE_PLACEHOLDERS})",
        (status, shift_id, *ACTIVE_REQUEST_STATUSES),
    )


def copy_previous_week(db, target_monday, created_by):
    """Копирует смены прошлой недели в указанную. Возвращает (скопировано, пропущено)."""
    source = shifts_between(db, target_monday - timedelta(days=7), target_monday - timedelta(days=1))
    copied = skipped = 0
    with db:
        for shift in source:
            if shift["status"] == "cancelled":
                continue
            new_date = parse_date(shift["date"]) + timedelta(days=7)
            if find_overlap(db, shift["user_id"], new_date, shift["start_time"], shift["end_time"]):
                skipped += 1
                continue
            insert_shift(db, {**shift, "date": new_date.isoformat()}, created_by)
            copied += 1
    return copied, skipped
