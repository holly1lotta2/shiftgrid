"""Замены смен: создание, проверки, переходы статусов."""
from datetime import date, datetime

from ..constants import (
    ACTIVE_REQUEST_STATUSES,
    MAX_REASON_LENGTH,
    MIN_REASON_LENGTH,
)
from ..timeutils import shift_bounds
from .shifts import ACTIVE_PLACEHOLDERS, SHIFT_WITH_USER_SQL, close_active_requests, decorate, find_overlap

REQUEST_SQL = """
SELECT r.id, r.shift_id, r.from_user_id, r.to_user_id, r.reason, r.status,
       r.created_at, r.updated_at,
       fu.full_name AS from_name, tu.full_name AS to_name,
       s.date AS shift_date, s.start_time, s.end_time, s.position
FROM swap_requests r
JOIN users fu ON fu.id = r.from_user_id
JOIN users tu ON tu.id = r.to_user_id
JOIN shifts s ON s.id = r.shift_id
"""
REQUEST_ORDER = (
    " ORDER BY CASE WHEN r.status IN ('pending_colleague', 'pending_manager') THEN 0 ELSE 1 END,"
    " s.date, r.id DESC"
)


def list_requests(db, condition="", params=(), limit=None):
    """condition — фрагмент WHERE из кода приложения, значения — только через params."""
    sql = REQUEST_SQL + (f" WHERE {condition}" if condition else "") + REQUEST_ORDER
    if limit:
        sql += " LIMIT ?"
        params = (*params, limit)
    now = datetime.now()
    items = []
    for row in db.execute(sql, params).fetchall():
        item = dict(row)
        item["is_past"] = shift_bounds(row["shift_date"], row["start_time"], row["end_time"])[0] <= now
        items.append(item)
    return items


def get_request(db, request_id):
    return db.execute("SELECT * FROM swap_requests WHERE id = ?", (request_id,)).fetchone()


def requestable_shifts(db, user_id):
    """Свои будущие запланированные смены без активного запроса на замену."""
    rows = db.execute(
        SHIFT_WITH_USER_SQL + " WHERE s.user_id = ? AND s.status = 'planned' AND s.date >= ? "
        "AND NOT EXISTS (SELECT 1 FROM swap_requests r WHERE r.shift_id = s.id "
        f"AND r.status IN ({ACTIVE_PLACEHOLDERS})) ORDER BY s.date, s.start_time",
        (user_id, date.today().isoformat(), *ACTIVE_REQUEST_STATUSES),
    ).fetchall()
    now = datetime.now()
    return [decorate(row, now) for row in rows
            if shift_bounds(row["date"], row["start_time"], row["end_time"])[0] > now]


def shift_problem(db, shift_id, owner_id, substitute_id):
    """Почему смену нельзя передать замене, или None."""
    shift = db.execute("SELECT * FROM shifts WHERE id = ?", (shift_id,)).fetchone()
    if shift is None or shift["user_id"] != owner_id:
        return "Смена не найдена среди смен сотрудника, который просит замену."
    if shift["status"] != "planned":
        return "Смена уже отменена или отработана."
    if shift_bounds(shift["date"], shift["start_time"], shift["end_time"])[0] <= datetime.now():
        return "Смена уже началась или прошла."
    if find_overlap(db, substitute_id, shift["date"], shift["start_time"], shift["end_time"]):
        return "У сотрудника на замене уже есть смена в это время."
    return None


def validate_new_request(db, user_id, form):
    """Возвращает (данные, ошибки) для нового запроса на замену."""
    shift_id = form.get("shift_id", type=int)
    to_user_id = form.get("to_user_id", type=int)
    reason = form.get("reason", "").strip()
    errors = []

    # Смена ищется по id И владельцу — чужую смену не передать даже подделкой формы.
    own_shift = db.execute(
        "SELECT id FROM shifts WHERE id = ? AND user_id = ?", (shift_id, user_id)
    ).fetchone()
    if own_shift is None:
        errors.append("Выберите свою смену.")
    elif db.execute(
        f"SELECT 1 FROM swap_requests WHERE shift_id = ? AND status IN ({ACTIVE_PLACEHOLDERS})",
        (shift_id, *ACTIVE_REQUEST_STATUSES),
    ).fetchone():
        errors.append("По этой смене уже есть активный запрос.")

    colleague = db.execute(
        "SELECT id FROM users WHERE id = ? AND role = 'employee' AND id != ?",
        (to_user_id, user_id),
    ).fetchone()
    if colleague is None:
        errors.append("Выберите коллегу.")
    if not MIN_REASON_LENGTH <= len(reason) <= MAX_REASON_LENGTH:
        errors.append(f"Причина: от {MIN_REASON_LENGTH} до {MAX_REASON_LENGTH} символов.")

    if not errors:
        problem = shift_problem(db, shift_id, user_id, colleague["id"])
        if problem:
            errors.append(problem)

    data = {"shift_id": shift_id, "to_user_id": to_user_id, "reason": reason}
    return data, errors


def create_request(db, user_id, data):
    with db:
        db.execute(
            "INSERT INTO swap_requests (shift_id, from_user_id, to_user_id, reason) VALUES (?, ?, ?, ?)",
            (data["shift_id"], user_id, data["to_user_id"], data["reason"]),
        )


def set_status(db, request_id, status):
    with db:
        db.execute(
            "UPDATE swap_requests SET status = ?, updated_at = datetime('now', 'localtime') WHERE id = ?",
            (status, request_id),
        )


def approve(db, req):
    """Передаёт смену коллеге; остальные активные запросы по смене закрываются."""
    with db:
        db.execute("UPDATE shifts SET user_id = ? WHERE id = ?", (req["to_user_id"], req["shift_id"]))
        db.execute(
            "UPDATE swap_requests SET status = 'approved', updated_at = datetime('now', 'localtime') "
            "WHERE id = ?",
            (req["id"],),
        )
        close_active_requests(db, req["shift_id"], "cancelled")
