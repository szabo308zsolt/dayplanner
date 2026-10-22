from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def hm_to_min(value):
    """'09:30' -> 570. Raises ValueError on bad input."""
    hh, mm = value.strip().split(":")[:2]
    hh, mm = int(hh), int(mm)
    if not (0 <= hh <= 24 and 0 <= mm < 60) or hh * 60 + mm > 1440:
        raise ValueError(value)
    return hh * 60 + mm


def min_to_hm(minutes):
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def fmt_duration(minutes):
    h, m = divmod(minutes, 60)
    if h and m:
        return f"{h}h {m}m"
    return f"{h}h" if h else f"{m}m"


def valid_timezone(name):
    try:
        ZoneInfo(name)
        return True
    except (ZoneInfoNotFoundError, ValueError):
        return False


def timezone_names():
    return sorted(available_timezones())


def now_in(tz):
    return datetime.now(ZoneInfo(tz))


def today_in(tz):
    return now_in(tz).date()


def minute_of_day(tz):
    n = now_in(tz)
    return n.hour * 60 + n.minute


def parse_date(value):
    return date.fromisoformat(value)


def next_working_day(day, work_days):
    for i in range(1, 8):
        candidate = day + timedelta(days=i)
        if candidate.weekday() in work_days:
            return candidate
    return day + timedelta(days=1)
