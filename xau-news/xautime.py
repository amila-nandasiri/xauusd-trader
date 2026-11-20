"""Gold market clock. Standard library only, no time zone files.

Spot gold (XAUUSD) trades from Sunday 18:00 to Friday 17:00 New York time,
with a daily break 17:00-18:00 New York time. Brokers (FP Markets included)
follow this, give or take a few minutes; check your MT5 symbol specification
(right-click XAUUSD > Specification > Sessions) and edit the config if yours differs.

Sessions, each in its own city's local time:
  asia    Tokyo    09:00-18:00 (no DST)
  london  London   08:00-17:00 (BST last Sun Mar - last Sun Oct)
  newyork New York 08:00-17:00 (EDT 2nd Sun Mar - 1st Sun Nov)
"""
import datetime as dt

UTC = dt.timezone.utc


def _nth_sunday(year, month, n):
    d = dt.date(year, month, 1)
    d += dt.timedelta(days=(6 - d.weekday()) % 7)
    return d + dt.timedelta(weeks=n - 1)


def _last_sunday(year, month):
    nxt = dt.date(year + (month == 12), month % 12 + 1, 1)
    d = nxt - dt.timedelta(days=1)
    return d - dt.timedelta(days=(d.weekday() + 1) % 7)


def ny_offset(t):
    """UTC offset in hours for New York at UTC instant t."""
    y = t.year
    start = dt.datetime.combine(_nth_sunday(y, 3, 2), dt.time(7), UTC)   # 2am EST = 07:00 UTC
    end = dt.datetime.combine(_nth_sunday(y, 11, 1), dt.time(6), UTC)    # 2am EDT = 06:00 UTC
    return -4 if start <= t < end else -5


def london_offset(t):
    y = t.year
    start = dt.datetime.combine(_last_sunday(y, 3), dt.time(1), UTC)
    end = dt.datetime.combine(_last_sunday(y, 10), dt.time(1), UTC)
    return 1 if start <= t < end else 0


def city_time(t, city):
    off = {"newyork": ny_offset, "london": london_offset}.get(city)
    hours = off(t) if off else 9  # Tokyo
    return t + dt.timedelta(hours=hours)


SESSIONS = {"asia": ("tokyo", 9, 18), "london": ("london", 8, 17), "newyork": ("newyork", 8, 17)}


def sessions_now(t):
    out = []
    for name, (city, a, b) in SESSIONS.items():
        lt = city_time(t, city)
        if lt.weekday() < 5 and a <= lt.hour < b:
            out.append(name)
    return out


def market_open(t):
    """(open?, reason) for spot gold at UTC instant t."""
    ny = city_time(t, "newyork")
    wd, h = ny.weekday(), ny.hour  # Mon=0 .. Sun=6
    if wd == 5:
        return False, "weekend (Saturday)"
    if wd == 6 and h < 18:
        return False, "weekend (opens Sunday 18:00 New York time)"
    if wd == 4 and h >= 17:
        return False, "weekend (closed Friday 17:00 New York time)"
    if h == 17:
        return False, "daily break 17:00-18:00 New York time"
    return True, "open"


def next_open(t):
    probe = t.replace(second=0, microsecond=0)
    for _ in range(60 * 24 * 3):
        probe += dt.timedelta(minutes=1)
        if market_open(probe)[0]:
            return probe
    return None


def now_utc():
    return dt.datetime.now(UTC)


def parse_when(s):
    """ISO time; naive means UTC."""
    t = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    return t if t.tzinfo else t.replace(tzinfo=UTC)


def local(t, offset_hours):
    return t.astimezone(dt.timezone(dt.timedelta(hours=offset_hours)))
