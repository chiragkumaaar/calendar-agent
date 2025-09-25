# src/check_freebusy.py
from __future__ import print_function
import argparse
import datetime
from googleapiclient.discovery import build
from google_auth_helpers import get_creds_from_env_or_local

SCOPES = ["https://www.googleapis.com/auth/calendar"]

def iso(dt):
    return dt.isoformat() + "Z"

def query_freebusy(service, emails, start_dt, end_dt):
    items = [{"id": email} for email in emails]
    body = {
        "timeMin": iso(start_dt),
        "timeMax": iso(end_dt),
        "timeZone": "UTC",
        "items": items
    }
    resp = service.freebusy().query(body=body).execute()
    return resp.get("calendars", {})

def pretty_print_busy(calendars):
    for email, cal in calendars.items():
        busy = cal.get("busy", [])
        print(f"\n=== {email} ===")
        if not busy:
            print("No busy slots in the window (appears free).")
            continue
        for b in busy:
            start = b.get("start")
            end = b.get("end")
            print(f"Busy: {start} -> {end}")

def main():
    parser = argparse.ArgumentParser(description="Check freebusy for attendees (using env secrets or token.json)")
    parser.add_argument("--attendees", "-a", required=True,
                        help="Comma-separated list of attendee emails (e.g. a@x.com,b@y.com)")
    parser.add_argument("--days", "-d", type=int, default=7,
                        help="Number of days from today to check (default 7)")
    parser.add_argument("--start", help="Optional start date ISO (YYYY-MM-DD). If omitted, uses today UTC.")
    args = parser.parse_args()

    emails = [e.strip() for e in args.attendees.split(",") if e.strip()]
    if not emails:
        print("No attendees provided.")
        return

    # Use the same helper as the rest of the app
    creds = get_creds_from_env_or_local(SCOPES)
    service = build("calendar", "v3", credentials=creds)

    if args.start:
        start_dt = datetime.datetime.fromisoformat(args.start)
    else:
        start_dt = datetime.datetime.utcnow()

    end_dt = start_dt + datetime.timedelta(days=args.days)

    print(f"Querying free/busy for {len(emails)} attendees from {start_dt.isoformat()} to {end_dt.isoformat()} (UTC)...")
    calendars = query_freebusy(service, emails, start_dt, end_dt)
    pretty_print_busy(calendars)

if __name__ == "__main__":
    main()
