"""Timezone-aware "what day is it" helpers.

Bug fix: the whole pipeline used to compute "today" via naive
datetime.date.today(), which resolves in the RUNNER's system timezone
(UTC on a standard GitHub Actions runner) -- but this product's actual
clock is unambiguously Asia/Tehran (UTC+3:30), which is why every cron
time in .github/workflows/ has a comment translating it to Tehran local
time. Since Tehran is UTC+3:30, Tehran midnight falls at UTC 20:30 the
*previous* day -- so any run between UTC 20:30-24:00 used to compute a
Python "today" one calendar day behind the real Tehran date, with no
margin against GitHub Actions' own well-documented scheduling delays and
zero protection for a manual workflow_dispatch run triggered at any time
of day.

This uses a fixed UTC offset (config.TEHRAN_UTC_OFFSET_HOURS) rather than
zoneinfo/pytz because Iran has not observed daylight saving time since
September 2022 (abolished permanently by parliament), so a fixed +3:30
offset is accurate year-round and needs no timezone database or extra
dependency. If Iran ever reinstates DST, update that one constant in
config.py.
"""
import datetime

from config import TEHRAN_UTC_OFFSET_HOURS

# Locale-independent — see weekday_name() below for why this matters.
_WEEKDAY_NAMES = [
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
]


def now():
    """Current datetime in the channel's own timezone (timezone-aware)."""
    utc_now = datetime.datetime.now(datetime.timezone.utc)
    offset = datetime.timedelta(hours=TEHRAN_UTC_OFFSET_HOURS)
    return utc_now.astimezone(datetime.timezone(offset))


def today():
    """Today's date in the channel's own timezone, as a datetime.date."""
    return now().date()


def today_str():
    """Today's date in the channel's own timezone, as an ISO string —
    the same format every data/*.json file already stores dates in."""
    return str(today())


def weekday_name(date=None):
    """English weekday name for `date` (default: today), independent of
    the process's locale.

    Bug fix: this used to be date.strftime("%A"), which is
    locale-dependent. A runner configured with any locale other than one
    that happens to produce English day names would silently and
    completely fail to match any key in data/format_schedule.json (whose
    keys are hardcoded English names) -- defaulting the entire weekly
    rotation to the fallback format, every day, with no error of any
    kind. date.weekday() returns a locale-independent integer
    (Monday=0..Sunday=6), so indexing a fixed English name list can never
    be affected by the environment's locale.
    """
    if date is None:
        date = today()
    return _WEEKDAY_NAMES[date.weekday()]
