import csv
import os
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
from . import StringConvertor as StrConv
import recurring_ical_events    
import requests
from icalendar import Calendar

load_dotenv = load_dotenv()

# Event names that feed the pay-period totals (exact match, case-insensitive).
WORK_EVENT_NAME = os.environ.get("WORK_EVENT_NAME", "").strip()
TIME_OFF_EVENT_NAME = os.environ.get("TIME_OFF_EVENT_NAME", "").strip()

def parsePayPeriod():
    payPeriodType = os.environ.get("PAY_PERIOD_TYPE", "")
    if payPeriodType != 'daily' and payPeriodType != 'weekly' and payPeriodType != 'biweekly' and payPeriodType != 'monthly':
        print('Invalid Pay Period!')
        sys.exit(7)
        return None
    if payPeriodType == 'daily':
        daysToPay = 1
    elif payPeriodType == 'weekly':
        daysToPay = 7
    elif payPeriodType == 'biweekly':
        daysToPay = 14
    else:
        daysToPay = 30
    return daysToPay

daysToPay = parsePayPeriod()

TZ = os.environ.get("TIMEZONE", "").strip()
LOCAL_TIMEZONE = ZoneInfo(TZ)

# File structure setup
PROJECT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_DIR / "data"
OUTPUT_FILE = OUTPUT_DIR / "calendar.csv"
PERIODS_FILE = OUTPUT_DIR / "pay_periods.csv"

today2 = date.today()
# PAST_PAY_PERIOD is the date a past pay period ENDED, so the next period
# starts the day after. Periods are laid out back and forth from that start
# date in steps of daysToPay.
PAY_PERIOD_ANCHOR = StrConv.Date(os.environ.get("PAST_PAY_PERIOD", "").strip()) + timedelta(days=1)
payPeriodHistory = today2 - PAY_PERIOD_ANCHOR

DAYS_BEFORE = (payPeriodHistory.days + daysToPay)
DAYS_AHEAD = 365
REQUEST_TIMEOUT_SECONDS = 30

CSV_COLUMNS = [
    "uid",
    "summary",
    "start",
    "end",
    "all_day",
    "duration_minutes",
    "location",
    "description",
    "status",
    "last_modified",
]

PERIOD_COLUMNS = [
    "period_start",
    "period_end",
    "hours_worked",
    "hours_excluded",
    "days_off",
]


def fail(message: str, exit_code: int = 1) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    sys.exit(exit_code)


def get_text(component, property_name: str) -> str:
    value = component.get(property_name)
    return str(value) if value is not None else ""


def normalize_datetime(value: datetime | date) -> datetime:
    """Convert a datetime/date to timezone-aware local datetime."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=LOCAL_TIMEZONE)
        return value.astimezone(LOCAL_TIMEZONE)

    return datetime.combine(value, datetime.min.time(), tzinfo=LOCAL_TIMEZONE)


def isoformat_local(value: datetime) -> str:
    """Format a local datetime in an unambiguous ISO-8601 form."""
    return value.isoformat(timespec="minutes")


def elapsed_seconds(start: datetime, end: datetime) -> float:
    """Real elapsed time. Subtracting two datetimes that share the same
    ZoneInfo ignores UTC offsets, so a span across a DST change would be
    off by an hour. Converting to UTC first avoids that."""
    return (end.astimezone(timezone.utc) - start.astimezone(timezone.utc)).total_seconds()


def parse_event(event) -> tuple[dict, datetime, datetime]:
    start_value = event.decoded("DTSTART")
    start_is_all_day = isinstance(start_value, date) and not isinstance(start_value, datetime)

    if event.get("DTEND") is not None:
        end_value = event.decoded("DTEND")
    elif event.get("DURATION") is not None:
        end_value = start_value + event.decoded("DURATION")
    elif start_is_all_day:
        end_value = start_value + timedelta(days=1)
    else:
        end_value = start_value

    start = normalize_datetime(start_value)
    end = normalize_datetime(end_value)

    duration_minutes = round(elapsed_seconds(start, end) / 60)

    row = {
        "uid": get_text(event, "UID"),
        "summary": get_text(event, "SUMMARY"),
        "start": isoformat_local(start),
        "end": isoformat_local(end),
        "all_day": "true" if start_is_all_day else "false",
        "duration_minutes": duration_minutes,
        "location": get_text(event, "LOCATION"),
        "description": get_text(event, "DESCRIPTION").replace("\r\n", "\n"),
        "status": get_text(event, "STATUS"),
        "last_modified": get_text(event, "LAST-MODIFIED"),
    }
    return row, start, end


# ---------------------------------------------------------------------------
# Pay-period bucketing
# ---------------------------------------------------------------------------

def period_start_for(day: date) -> date:
    """First day of the pay period containing `day`."""
    periods_elapsed = (day - PAY_PERIOD_ANCHOR).days // daysToPay
    return PAY_PERIOD_ANCHOR + timedelta(days=periods_elapsed * daysToPay)


def bucket(totals: dict, period_start: date) -> dict:
    return totals.setdefault(
        period_start,
        {"hours_worked": 0.0, "hours_excluded": 0.0, "days_off": 0},
    )


def build_period_totals(range_start: datetime, range_end: datetime) -> dict:
    """One entry per pay period in range, so empty periods still appear as zeros."""
    totals: dict = {}
    period_start = period_start_for(range_start.date())
    while period_start <= range_end.date():
        bucket(totals, period_start)
        period_start += timedelta(days=daysToPay)
    return totals


def covered_days(start: datetime, end: datetime) -> list[date]:
    """Calendar days an event touches. All-day DTEND is exclusive, so the last
    covered day is the one containing the instant before `end`."""
    last_day = max(start, end - timedelta(microseconds=1)).date()
    days = []
    day = start.date()
    while day <= last_day:
        days.append(day)
        day += timedelta(days=1)
    return days


def add_work_hours(totals: dict, off_days: set, start: datetime, end: datetime) -> None:
    """Add worked hours one local calendar day at a time. Time that falls on a
    day off is not counted as worked; it goes to hours_excluded instead."""
    cursor = start
    while cursor < end:
        next_midnight = datetime.combine(
            cursor.date() + timedelta(days=1),
            time.min,
            tzinfo=LOCAL_TIMEZONE,
        )
        segment_end = min(end, next_midnight)
        hours = elapsed_seconds(cursor, segment_end) / 3600
        period = bucket(totals, period_start_for(cursor.date()))
        if cursor.date() in off_days:
            period["hours_excluded"] += hours
        else:
            period["hours_worked"] += hours
        cursor = segment_end


def add_days_off(totals: dict, off_days: set) -> None:
    """Count each distinct day off once, in the pay period containing it
    (overlapping time-off events don't double count)."""
    for day in off_days:
        bucket(totals, period_start_for(day))["days_off"] += 1


def download_calendar(ics_url: str) -> Calendar:
    try:
        response = requests.get(
            ics_url,
            timeout=REQUEST_TIMEOUT_SECONDS,
            headers={"User-Agent": "calendar-calc-importer/1.0"},
        )
        response.raise_for_status()
    except requests.RequestException as error:
        fail(f"Could not download ICS feed: {error}")

    if not response.content:
        fail("ICS feed download was empty.")

    try:
        return Calendar.from_ical(response.content)
    except Exception as error:
        fail(f"Downloaded content is not a valid ICS calendar: {error}")


def write_csv(path: Path, columns: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    temporary_file = path.with_suffix(".csv.tmp")

    try:
        with temporary_file.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows)

        temporary_file.replace(path)
    except OSError as error:
        fail(f"Could not write CSV file {path}: {error}")


def main() -> None:
    ics_url = os.environ.get("ICS_URL", "").strip()

    if not ics_url:
        fail(
            "ICS_URL is not set. "
            "Check the .env file"
        )

    if not ics_url.startswith(("https://", "http://")):
        fail("ICS_URL must start with https:// or http://.")

    now = datetime.now(LOCAL_TIMEZONE)
    # Start at local midnight so events earlier in the first day aren't dropped.
    range_start = datetime.combine(
        now.date() - timedelta(days=DAYS_BEFORE),
        time.min,
        tzinfo=LOCAL_TIMEZONE,
    )
    range_end = now + timedelta(days=DAYS_AHEAD)

    calendar = download_calendar(ics_url)

    try:
        expanded_events = recurring_ical_events.of(calendar).between(
            range_start,
            range_end,
        )
    except Exception as error:
        fail(f"Could not expand recurring events: {error}")

    rows = []
    period_totals = build_period_totals(range_start, range_end)
    ignored_names = set()
    work_shifts = []
    off_days = set()
    work_name = WORK_EVENT_NAME.casefold()
    time_off_name = TIME_OFF_EVENT_NAME.casefold()

    for event in expanded_events:
        try:
            row, start, end = parse_event(event)
            rows.append(row)

            if row["status"].upper() == "CANCELLED":
                continue

            name = row["summary"].strip().casefold()
            if name == work_name:
                work_shifts.append((start, end))
            elif name == time_off_name:
                off_days.update(covered_days(start, end))
            else:
                ignored_names.add(row["summary"])
        except Exception as error:
            uid = get_text(event, "UID") or "<no UID>"
            print(
                f"WARNING: Skipping malformed event UID={uid}: {error}",
                file=sys.stderr,
            )

    # Days off are only known once every event has been read, so tally now.
    add_days_off(period_totals, off_days)
    for start, end in work_shifts:
        add_work_hours(period_totals, off_days, start, end)

    rows.sort(key=lambda row: (row["start"], row["summary"], row["uid"]))

    write_csv(OUTPUT_FILE, CSV_COLUMNS, rows)

    period_rows = [
        {
            "period_start": period_start.isoformat(),
            "period_end": (period_start + timedelta(days=daysToPay - 1)).isoformat(),
            "hours_worked": round(totals["hours_worked"], 4),
            "hours_excluded": round(totals["hours_excluded"], 4),
            "days_off": totals["days_off"],
        }
        for period_start, totals in sorted(period_totals.items())
    ]
    write_csv(PERIODS_FILE, PERIOD_COLUMNS, period_rows)

    if ignored_names:
        print(
            f"NOTE: Ignored events not named '{WORK_EVENT_NAME}' or "
            f"'{TIME_OFF_EVENT_NAME}': {', '.join(sorted(ignored_names))}",
            file=sys.stderr,
        )

    if rows:
        first_day = rows[0]["start"].split("T")[0]
        last_day = rows[-1]["start"].split("T")[0]
        pass
    else:
        pass