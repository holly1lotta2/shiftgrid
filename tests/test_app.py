"""Сквозные сценарии через HTTP: доступ, страницы, смены, отчёты, профиль."""
from datetime import date, timedelta

import pytest

from app.timeutils import add_months, week_start

MANAGER_PAGES = [
    "/dashboard", "/schedule", "/schedule?view=month", "/schedule?view=week&date=2026-01-05",
    "/employees", "/shifts/new", "/requests", "/requests?tab=closed", "/requests?tab=all", "/profile",
]
EMPLOYEE_PAGES = ["/dashboard", "/schedule", "/schedule?view=month", "/colleagues", "/requests", "/profile"]


def future(days):
    return (date.today() + timedelta(days=days)).isoformat()


# ---------------------------------------------------------------- доступ

def test_anonymous_is_redirected_to_login(client):
    assert client.get("/").status_code == 302
    assert "/login" in client.get("/schedule").headers["Location"]


def test_post_without_csrf_is_rejected(client):
    assert client.raw.post("/login", data={"username": "manager"}).status_code == 400


def test_login_page_offers_demo_accounts(client):
    html = client.text("/login")
    assert 'data-demo-username="manager"' in html and 'data-demo-username="olga"' in html


def test_wrong_password_returns_401(client):
    assert client.login("manager", "wrong").status_code == 401


def test_open_redirect_is_blocked(client):
    response = client.post("/login", {"username": "manager", "password": "manager123", "next": "//evil.com"})
    assert response.headers["Location"] == "/dashboard"


@pytest.mark.parametrize("url", MANAGER_PAGES)
def test_manager_pages_open(manager, url):
    assert manager.get(url).status_code == 200


@pytest.mark.parametrize("url", EMPLOYEE_PAGES)
def test_employee_pages_open(make_client, url):
    assert make_client("ivan").get(url).status_code == 200


@pytest.mark.parametrize("url", ["/employees", "/shifts/new", "/employees/report.csv"])
def test_employee_cannot_open_manager_pages(make_client, url):
    assert make_client("ivan").get(url).status_code == 403


def test_manager_cannot_open_colleagues(manager):
    assert manager.get("/colleagues").status_code == 403


def test_employee_cannot_edit_or_delete_shifts(make_client, db, ids):
    ivan = make_client("ivan")
    maria_shift = db.execute("SELECT id FROM shifts WHERE user_id = ?", (ids["maria"],)).fetchone()["id"]
    assert ivan.post(f"/shifts/{maria_shift}/edit", {"user_id": ids["ivan"]}).status_code == 403
    assert ivan.post(f"/shifts/{maria_shift}/delete").status_code == 403


def test_employee_sees_only_own_shifts(make_client, ids):
    html = make_client("ivan").text(f"/schedule?view=month&employee={ids['maria']}")
    assert "Бариста" in html
    assert "Кассир" not in html and "Официант" not in html and "Повар" not in html


def test_logout(make_client):
    ivan = make_client("ivan")
    ivan.post("/logout")
    assert ivan.get("/dashboard").status_code == 302


# ---------------------------------------------------------------- демо-данные

def test_seed_creates_team_shifts_and_two_swaps(db):
    assert db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 5
    assert db.execute("SELECT COUNT(*) FROM shifts").fetchone()[0] > 20
    statuses = sorted(r[0] for r in db.execute("SELECT status FROM swap_requests"))
    assert statuses == ["pending_colleague", "pending_manager"]


def test_finished_shifts_are_completed_automatically(manager, db):
    rows = db.execute("SELECT status FROM shifts WHERE date < ?", (date.today().isoformat(),)).fetchall()
    assert rows and all(r["status"] == "completed" for r in rows)


def test_week_grid_shows_all_employees(manager):
    html = manager.text("/schedule")
    for name in ("Иван Петров", "Мария Иванова", "Пётр Сидоров", "Ольга Ким"):
        assert name in html


# ---------------------------------------------------------------- смены

@pytest.fixture()
def shift_form(ids):
    return {"user_id": ids["peter"], "date": future(40), "position": "Официант"}


@pytest.mark.parametrize("times, message", [
    ({"start_time": "18:00", "end_time": "10:00"}, "раньше начала"),
    ({"start_time": "10:00", "end_time": "10:00"}, "совпадают"),
    ({"start_time": "10:00", "end_time": "18:00", "overnight": "1"}, "окончание позже начала"),
    ({"start_time": "06:00", "end_time": "23:30"}, "дольше 16"),
])
def test_invalid_shift_times_are_rejected(manager, shift_form, times, message):
    response = manager.post("/shifts/new", {**shift_form, **times})
    assert response.status_code == 400
    assert message in response.get_data(as_text=True)


def test_overnight_shift_and_overlap_check(manager, shift_form, db):
    created = manager.post("/shifts/new", {**shift_form, "start_time": "22:00", "end_time": "06:00", "overnight": "1"})
    assert created.status_code == 302
    overlap = manager.post("/shifts/new", {**shift_form, "date": future(41), "start_time": "05:00", "end_time": "09:00"})
    assert overlap.status_code == 400 and "пересекается" in overlap.get_data(as_text=True)


def test_shift_for_manager_is_rejected(manager, shift_form, ids):
    response = manager.post("/shifts/new", {**shift_form, "user_id": ids["manager"],
                                            "start_time": "10:00", "end_time": "12:00"})
    assert response.status_code == 400


def test_sql_injection_is_stored_as_text(manager, shift_form, db):
    before = db.execute("SELECT COUNT(*) FROM shifts").fetchone()[0]
    manager.post("/shifts/new", {**shift_form, "position": "x'); DROP TABLE shifts; --",
                                 "start_time": "10:00", "end_time": "12:00"})
    assert db.execute("SELECT COUNT(*) FROM shifts").fetchone()[0] == before + 1


def test_edit_and_cancel_shift_closes_active_swaps(manager, db):
    req = db.execute("SELECT * FROM swap_requests WHERE status = 'pending_colleague'").fetchone()
    shift = db.execute("SELECT * FROM shifts WHERE id = ?", (req["shift_id"],)).fetchone()
    response = manager.post(f"/shifts/{shift['id']}/edit", {
        "user_id": shift["user_id"], "date": shift["date"], "start_time": shift["start_time"],
        "end_time": shift["end_time"], "position": shift["position"], "status": "cancelled",
    })
    assert response.status_code == 302
    assert db.execute("SELECT status FROM swap_requests WHERE id = ?", (req["id"],)).fetchone()[0] == "cancelled"


def test_delete_shift(manager, shift_form, db):
    manager.post("/shifts/new", {**shift_form, "start_time": "10:00", "end_time": "12:00"})
    shift_id = db.execute("SELECT MAX(id) FROM shifts").fetchone()[0]
    assert manager.post(f"/shifts/{shift_id}/delete").status_code == 302
    assert db.execute("SELECT COUNT(*) FROM shifts WHERE id = ?", (shift_id,)).fetchone()[0] == 0


def test_copy_previous_week(manager, db):
    target = week_start(date.today()) + timedelta(days=14)  # демо заканчивается на следующей неделе
    response = manager.post("/schedule/copy-week", {"week": target.isoformat()})
    assert response.status_code == 302
    copied = db.execute("SELECT COUNT(*) FROM shifts WHERE date BETWEEN ? AND ?",
                        (target.isoformat(), (target + timedelta(days=6)).isoformat())).fetchone()[0]
    assert copied == 16
    manager.post("/schedule/copy-week", {"week": target.isoformat()})
    again = db.execute("SELECT COUNT(*) FROM shifts WHERE date BETWEEN ? AND ?",
                       (target.isoformat(), (target + timedelta(days=6)).isoformat())).fetchone()[0]
    assert again == 16, "повторное копирование не должно создавать дубли"


def test_copy_into_past_week_is_refused(manager):
    past = week_start(date.today()) - timedelta(days=14)
    manager.post("/schedule/copy-week", {"week": past.isoformat()})
    assert "прошедшую неделю" in manager.text("/dashboard")


# ---------------------------------------------------------------- часы и отчёты

def test_overtime_is_highlighted_in_report(manager, ids):
    year, month = add_months(date.today().year, date.today().month, 2)
    for day in range(1, 22):
        manager.post("/shifts/new", {"user_id": ids["ivan"], "date": date(year, month, day).isoformat(),
                                     "start_time": "08:00", "end_time": "16:00", "position": "Бариста"})
    html = manager.text(f"/employees?year={year}&month={month}")
    assert "+8 ч" in html and "text-overtime" in html


def test_csv_report_downloads(manager):
    response = manager.get("/employees/report.csv")
    assert response.status_code == 200
    assert "attachment" in response.headers["Content-Disposition"]
    body = response.get_data(as_text=True)
    assert body.startswith("﻿Сотрудник;Логин") and "Мария Иванова" in body


# ---------------------------------------------------------------- сотрудники

def test_add_edit_delete_employee(manager, db):
    bad = manager.post("/employees", {"full_name": "Анна Ли", "username": "anna", "password": "123"})
    assert bad.status_code == 400
    ok = manager.post("/employees", {"full_name": "Анна Ли", "username": "Anna", "password": "123456",
                                     "position": "Хостес", "phone": "+7 900 1"})
    assert ok.status_code == 302
    duplicate = manager.post("/employees", {"full_name": "Дубль", "username": "anna", "password": "123456"})
    assert duplicate.status_code == 400

    anna = db.execute("SELECT id FROM users WHERE username = 'anna'").fetchone()["id"]
    manager.post(f"/employees/{anna}/edit", {"full_name": "Анна Ли", "position": "Бармен", "phone": "",
                                             "new_password": "secret1"})
    assert db.execute("SELECT position FROM users WHERE id = ?", (anna,)).fetchone()[0] == "Бармен"
    assert manager.post(f"/employees/{anna}/delete").status_code == 302
    assert db.execute("SELECT COUNT(*) FROM users WHERE id = ?", (anna,)).fetchone()[0] == 0


def test_manager_cannot_be_deleted_as_employee(manager, db, ids):
    manager.post(f"/employees/{ids['manager']}/delete")
    assert db.execute("SELECT COUNT(*) FROM users WHERE id = ?", (ids["manager"],)).fetchone()[0] == 1


# ---------------------------------------------------------------- профиль и данные

def test_change_password(make_client, app):
    ivan = make_client("ivan")
    ivan.post("/profile/password", {"current_password": "123456", "new_password": "abc",
                                    "new_password_confirm": "abc"})
    assert "не короче" in ivan.text("/profile")
    ivan.post("/profile/password", {"current_password": "123456", "new_password": "newpass1",
                                    "new_password_confirm": "newpass1"})
    assert make_client("ivan", "newpass1").get("/dashboard").status_code == 200


def test_clear_data_requires_confirm_word(manager, db):
    manager.post("/settings/clear", {"confirm": "да"})
    assert db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 5
    manager.post("/settings/clear", {"confirm": "удалить"})
    assert db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1
    assert db.execute("SELECT COUNT(*) FROM shifts").fetchone()[0] == 0
    assert "Пока нет сотрудников" in manager.text("/employees")


def test_reset_demo_restores_data_and_logs_out(manager, db):
    manager.post("/settings/clear", {"confirm": "УДАЛИТЬ"})
    response = manager.post("/settings/reset-demo")
    assert response.status_code == 302 and "/login" in response.headers["Location"]
    assert db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 5
    assert manager.get("/dashboard").status_code == 302
