"""Даты, время смен и перевод минут в часы."""
import calendar
from datetime import date, datetime, timedelta

from .constants import (
    MINUTES_PER_DAY,
    MONTHLY_NORM_HOURS,
    RU_MONTHS_GENITIVE,
    RU_WEEKDAYS_SHORT,
)


def parse_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except (AttributeError, TypeError, ValueError):
        return None


def normalize_time(value):
    """'9:05' -> '09:05'; некорректное значение -> None."""
    try:
        return datetime.strptime(value.strip(), "%H:%M").strftime("%H:%M")
    except (AttributeError, TypeError, ValueError):
        return None


def to_minutes(hhmm):
    hours, minutes = hhmm.split(":")
    return int(hours) * 60 + int(minutes)


def duration_minutes(start_time, end_time):
    """Длительность смены. Конец раньше начала (или равен ему) — смена через полночь."""
    diff = to_minutes(end_time) - to_minutes(start_time)
    return diff if diff > 0 else diff + MINUTES_PER_DAY


def is_overnight(start_time, end_time):
    return to_minutes(end_time) <= to_minutes(start_time)


def shift_bounds(day, start_time, end_time):
    """Начало и конец смены как datetime (конец ночной смены — на следующий день)."""
    start = datetime.combine(parse_date(day), datetime.strptime(start_time, "%H:%M").time())
    return start, start + timedelta(minutes=duration_minutes(start_time, end_time))


def week_start(day):
    return day - timedelta(days=day.weekday())


def month_range(year, month):
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


def add_months(year, month, delta):
    index = year * 12 + month - 1 + delta
    return index // 12, index % 12 + 1


def to_hours(minutes):
    return round(minutes / 60, 2)


def overtime_of(hours):
    return round(max(0.0, hours - MONTHLY_NORM_HOURS), 2)


def norm_percent(hours):
    return min(100, round(hours / MONTHLY_NORM_HOURS * 100))


def ru_date(value):
    """'2026-10-22' -> 'Чт, 22 октября'."""
    day = parse_date(value)
    if day is None:
        return value
    return f"{RU_WEEKDAYS_SHORT[day.weekday()]}, {day.day} {RU_MONTHS_GENITIVE[day.month]}"


def relative_day(value):
    """'сегодня' / 'завтра' / 'Чт, 22 октября'."""
    day = parse_date(value)
    if day is None:
        return value
    delta = (day - date.today()).days
    if delta == 0:
        return "сегодня"
    if delta == 1:
        return "завтра"
    return ru_date(day)


def week_label(monday):
    """'20 – 26 октября 2026' или '27 октября – 2 ноября 2026'."""
    sunday = monday + timedelta(days=6)
    if monday.month == sunday.month:
        return f"{monday.day} – {sunday.day} {RU_MONTHS_GENITIVE[sunday.month]} {sunday.year}"
    return (f"{monday.day} {RU_MONTHS_GENITIVE[monday.month]} – "
            f"{sunday.day} {RU_MONTHS_GENITIVE[sunday.month]} {sunday.year}")
