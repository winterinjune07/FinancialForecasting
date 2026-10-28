#!/usr/bin/env python3

import csv
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import StringConvertor as StrConv
import recurring_ical_events
import requests
from icalendar import Calendar

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
PROJECT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = PROJECT_DIR / "data"
OUTPUT_FILE = OUTPUT_DIR / "calendar.csv"

today2 = date.today()
payPeriodHistory = today2 - (StrConv.Date(os.environ.get("PAST_PAY_PERIOD", "").strip()))

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


def parse_event(event) -> dict:
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

    duration_minutes = round((end - start).total_seconds() / 60)

    return {
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


def write_csv(rows: list[dict]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    temporary_file = OUTPUT_FILE.with_suffix(".csv.tmp")

    try:
        with temporary_file.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=CSV_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)

        temporary_file.replace(OUTPUT_FILE)
    except OSError as error:
        fail(f"Could not write CSV file {OUTPUT_FILE}: {error}")


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
    range_start = now - timedelta(days=DAYS_BEFORE)
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

    for event in expanded_events:
        try:
            rows.append(parse_event(event))
        except Exception as error:
            uid = get_text(event, "UID") or "<no UID>"
            print(
                f"WARNING: Skipping malformed event UID={uid}: {error}",
                file=sys.stderr,
            )



    rows.sort(key=lambda row: (row["start"], row["summary"], row["uid"]))

    write_csv(rows)

    temp1 = (list(rows[-1].values())[2])
    temp2 = (list(rows[0].values())[2])

    print(
        f"SUCCESS: Wrote {len(rows)} events"
        f"for {temp2.split('T')[0]} through "
        f"{temp1.split('T')[0]}."
    )


if __name__ == "__main__":
    main()