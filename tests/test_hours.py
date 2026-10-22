"""Расчёт часов и вспомогательные функции времени."""
from datetime import date

from app.filters import hours_filter
from app.timeutils import (
    add_months,
    duration_minutes,
    normalize_time,
    overtime_of,
    shift_bounds,
    week_label,
)


def test_overnight_shift_counts_eight_hours():
    assert duration_minutes("22:00", "06:00") == 480


def test_day_shift_and_short_overnight():
    assert duration_minutes("09:00", "17:00") == 480
    assert duration_minutes("23:30", "00:30") == 60


def test_overnight_shift_ends_next_day():
    start, end = shift_bounds("2026-10-30", "22:00", "06:00")
    assert start.date() == date(2026, 10, 30)
    assert end.date() == date(2026, 10, 31)


def test_overtime_is_hours_above_norm():
    assert overtime_of(168) == 8
    assert overtime_of(120) == 0


def test_hours_filter_formats_russian_decimal():
    assert hours_filter(7.5) == "7,5"
    assert hours_filter(8.0) == "8"


def test_normalize_time_and_month_math():
    assert normalize_time("9:05") == "09:05"
    assert normalize_time("25:00") is None
    assert add_months(2026, 12, 1) == (2027, 1)
    assert add_months(2026, 1, -1) == (2025, 12)


def test_week_label_across_months():
    assert week_label(date(2026, 10, 26)) == "26 октября – 1 ноября 2026"
    assert week_label(date(2026, 10, 19)) == "19 – 25 октября 2026"
