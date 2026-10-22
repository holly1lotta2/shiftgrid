"""Покрытие по часам: сколько людей на смене в каждый час дня и где «дыры» в графике."""
from datetime import datetime, timedelta

from ..timeutils import parse_date, shift_bounds, to_minutes

HOURS_IN_DAY = 24
HOUR = timedelta(hours=1)


def day_coverage(shifts, day):
    """24 числа — сколько неотменённых смен идёт в каждый час дня.

    Ночные смены прошлого дня тоже учитываются, поэтому в shifts можно передать и вчерашние.
    """
    day_start = datetime.combine(day, datetime.min.time())
    counts = [0] * HOURS_IN_DAY
    for shift in shifts:
        if shift["status"] == "cancelled":
            continue
        start, end = shift_bounds(shift["date"], shift["start_time"], shift["end_time"])
        for hour in range(HOURS_IN_DAY):
            slot = day_start + hour * HOUR
            if start < slot + HOUR and slot < end:
                counts[hour] += 1
    return counts


def working_span(shifts, day):
    """Часы от начала первой до конца последней смены, начавшейся в этот день: (с, по) или None."""
    starting = [s for s in shifts if parse_date(s["date"]) == day and s["status"] != "cancelled"]
    if not starting:
        return None
    first = min(to_minutes(s["start_time"]) // 60 for s in starting)
    last = max(min(HOURS_IN_DAY, (to_minutes(s["start_time"]) + s["minutes"] + 59) // 60) for s in starting)
    return first, last


def coverage_strip(shifts, day, peak):
    """Данные для полосы: столбик на каждый час; «дыра» — пустой час внутри рабочего дня."""
    counts = day_coverage(shifts, day)
    span = working_span(shifts, day)
    scale = max(peak, 1)
    bars = []
    for hour, count in enumerate(counts):
        gap = bool(span) and span[0] <= hour < span[1] and count == 0
        bars.append({"hour": hour, "count": count, "height": round(count / scale * 100), "gap": gap})
    return {"bars": bars, "gaps": sum(1 for bar in bars if bar["gap"]), "peak": max(counts)}


def week_strips(shifts, days):
    """Полосы на каждый день с общей шкалой, чтобы дни можно было сравнивать между собой."""
    counts = {day: day_coverage(shifts, day) for day in days}
    peak = max((max(c) for c in counts.values()), default=0)
    return {day.isoformat(): coverage_strip(shifts, day, peak) for day in days}
