"""Замены: сотрудник → коллега → управляющий."""
from datetime import date, timedelta

import pytest


FREE_WEEK = date.today() - timedelta(days=date.today().weekday()) + timedelta(days=14)


def requestable_shift(db, user_id, start="09:00", end="17:00"):
    """Смена через две недели — демо-график туда не доходит, все коллеги свободны."""
    cur = db.execute(
        "INSERT INTO shifts (user_id, date, start_time, end_time, position) VALUES (?, ?, ?, ?, 'Тест')",
        (user_id, FREE_WEEK.isoformat(), start, end),
    )
    db.commit()
    return cur.lastrowid


@pytest.fixture()
def ivan(make_client):
    return make_client("ivan")


def test_full_swap_flow(ivan, make_client, manager, db, ids):
    shift_id = requestable_shift(db, ids["ivan"])
    created = ivan.post("/requests", {"shift_id": shift_id, "to_user_id": ids["olga"], "reason": "Болею"})
    assert created.status_code == 302
    req_id = db.execute("SELECT id FROM swap_requests WHERE shift_id = ?", (shift_id,)).fetchone()["id"]

    # управляющий не может утвердить, пока коллега не согласился
    manager.post(f"/requests/{req_id}/approve")
    assert db.execute("SELECT status FROM swap_requests WHERE id = ?", (req_id,)).fetchone()[0] == "pending_colleague"

    olga = make_client("olga")
    assert "Вас просят подменить" in olga.text("/dashboard")
    olga.post(f"/requests/{req_id}/accept")
    assert db.execute("SELECT status FROM swap_requests WHERE id = ?", (req_id,)).fetchone()[0] == "pending_manager"

    manager.post(f"/requests/{req_id}/approve")
    assert db.execute("SELECT status FROM swap_requests WHERE id = ?", (req_id,)).fetchone()[0] == "approved"
    assert db.execute("SELECT user_id FROM shifts WHERE id = ?", (shift_id,)).fetchone()[0] == ids["olga"]


def test_cannot_request_swap_for_someone_elses_shift(ivan, db, ids):
    maria_shift = requestable_shift(db, ids["maria"])
    ivan.post("/requests", {"shift_id": maria_shift, "to_user_id": ids["peter"], "reason": "Чужая"})
    assert "Выберите свою смену" in ivan.text("/requests")
    assert db.execute("SELECT COUNT(*) FROM swap_requests WHERE shift_id = ?", (maria_shift,)).fetchone()[0] == 0


def test_cannot_request_swap_for_past_shift(ivan, db, ids):
    shift_id = requestable_shift(db, ids["ivan"])
    db.execute("UPDATE shifts SET date = ? WHERE id = ?", ((date.today() - timedelta(days=2)).isoformat(), shift_id))
    db.commit()
    ivan.post("/requests", {"shift_id": shift_id, "to_user_id": ids["peter"], "reason": "Поздно"})
    assert db.execute("SELECT COUNT(*) FROM swap_requests WHERE shift_id = ?", (shift_id,)).fetchone()[0] == 0


def test_cannot_ask_busy_colleague(ivan, db, ids):
    shift_id = requestable_shift(db, ids["ivan"], "09:00", "17:00")
    requestable_shift(db, ids["maria"], "10:00", "22:00")
    ivan.post("/requests", {"shift_id": shift_id, "to_user_id": ids["maria"], "reason": "Экзамен"})
    assert "уже есть смена в это время" in ivan.text("/requests")


def test_one_active_request_per_shift(ivan, db, ids):
    shift_id = requestable_shift(db, ids["ivan"])
    ivan.post("/requests", {"shift_id": shift_id, "to_user_id": ids["olga"], "reason": "Первый"})
    ivan.post("/requests", {"shift_id": shift_id, "to_user_id": ids["peter"], "reason": "Второй"})
    assert db.execute("SELECT COUNT(*) FROM swap_requests WHERE shift_id = ?", (shift_id,)).fetchone()[0] == 1


def test_only_addressee_can_accept_and_only_author_can_cancel(make_client, db):
    req = db.execute("SELECT * FROM swap_requests WHERE status = 'pending_colleague'").fetchone()
    assert make_client("maria").post(f"/requests/{req['id']}/accept").status_code == 403
    assert make_client("peter").post(f"/requests/{req['id']}/cancel").status_code == 403
    make_client("ivan").post(f"/requests/{req['id']}/cancel")
    assert db.execute("SELECT status FROM swap_requests WHERE id = ?", (req["id"],)).fetchone()[0] == "cancelled"


def test_decline_and_reject(make_client, manager, db):
    colleague_req = db.execute("SELECT * FROM swap_requests WHERE status = 'pending_colleague'").fetchone()
    manager_req = db.execute("SELECT * FROM swap_requests WHERE status = 'pending_manager'").fetchone()
    make_client("peter").post(f"/requests/{colleague_req['id']}/decline")
    manager.post(f"/requests/{manager_req['id']}/reject")
    assert db.execute("SELECT status FROM swap_requests WHERE id = ?", (colleague_req["id"],)).fetchone()[0] == "declined"
    assert db.execute("SELECT status FROM swap_requests WHERE id = ?", (manager_req["id"],)).fetchone()[0] == "rejected"


def test_employee_cannot_approve(make_client, db):
    req = db.execute("SELECT id FROM swap_requests WHERE status = 'pending_manager'").fetchone()
    assert make_client("olga").post(f"/requests/{req['id']}/approve").status_code == 403


def test_new_employee_sees_empty_states(manager, make_client):
    manager.post("/employees", {"full_name": "Новичок Новый", "username": "newbie", "password": "123456"})
    newbie = make_client("newbie")
    assert "Запланированных смен пока нет" in newbie.text("/dashboard")
    assert "Вы ещё не просили замену" in newbie.text("/requests")
