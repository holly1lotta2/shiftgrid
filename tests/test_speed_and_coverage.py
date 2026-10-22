"""Скорость загрузки (локальная статика, gzip, кэш) и полоса покрытия по часам."""
import gzip
from datetime import date

from app.logic.coverage import coverage_strip, day_coverage, week_strips
from app.timeutils import duration_minutes

DAY = date(2026, 10, 22)


def shift(day, start, end, status="planned"):
    return {"date": day, "start_time": start, "end_time": end, "status": status,
            "minutes": duration_minutes(start, end)}


def test_day_coverage_counts_people_per_hour():
    counts = day_coverage([shift("2026-10-22", "09:00", "17:00"), shift("2026-10-22", "14:00", "23:00")], DAY)
    assert counts[8] == 0 and counts[9] == 1 and counts[14] == 2 and counts[22] == 1 and counts[23] == 0


def test_previous_night_shift_spills_into_morning():
    counts = day_coverage([shift("2026-10-21", "22:00", "06:00")], DAY)
    assert counts[0] == 1 and counts[5] == 1 and counts[6] == 0


def test_cancelled_shifts_do_not_count():
    assert sum(day_coverage([shift("2026-10-22", "09:00", "17:00", "cancelled")], DAY)) == 0


def test_gap_inside_working_day_is_marked():
    shifts = [shift("2026-10-22", "08:00", "12:00"), shift("2026-10-22", "14:00", "18:00")]
    strip = coverage_strip(shifts, DAY, peak=1)
    assert strip["gaps"] == 2
    assert [b["hour"] for b in strip["bars"] if b["gap"]] == [12, 13]


def test_night_spill_does_not_create_false_gap():
    shifts = [shift("2026-10-21", "22:00", "06:00"), shift("2026-10-22", "09:00", "17:00")]
    assert coverage_strip(shifts, DAY, peak=1)["gaps"] == 0


def test_week_strips_share_one_scale():
    days = [date(2026, 10, 22), date(2026, 10, 23)]
    shifts = [shift("2026-10-22", "09:00", "10:00"), shift("2026-10-22", "09:00", "10:00"),
              shift("2026-10-23", "09:00", "10:00")]
    strips = week_strips(shifts, days)
    assert strips["2026-10-22"]["bars"][9]["height"] == 100
    assert strips["2026-10-23"]["bars"][9]["height"] == 50


def test_pages_use_local_assets_only(manager):
    html = manager.text("/schedule")
    assert "cdn.jsdelivr.net" not in html and "fonts.googleapis" not in html
    assert "/static/vendor/bootstrap.min.css?v=" in html


def test_week_view_shows_coverage_row(manager):
    html = manager.text("/schedule")
    assert "Люди по часам" in html and 'class="coverage' in html


def test_manager_dashboard_shows_today_coverage(manager):
    assert "Люди на месте по часам" in manager.text("/dashboard")


def test_html_is_gzipped_when_browser_accepts_it(manager):
    response = manager.get("/schedule", headers={"Accept-Encoding": "gzip"})
    assert response.headers["Content-Encoding"] == "gzip"
    assert "График смен" in gzip.decompress(response.data).decode("utf-8")


def test_static_files_are_cached_and_compressed(client):
    response = client.get("/static/vendor/bootstrap.min.css", headers={"Accept-Encoding": "gzip"})
    assert response.status_code == 200
    assert response.headers["Content-Encoding"] == "gzip"
    assert "max-age=31536000" in response.headers["Cache-Control"]
    assert len(response.data) < 60_000, "сжатый Bootstrap должен весить заметно меньше 230 КБ"
