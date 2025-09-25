# src/check_freebusy.py
from __future__ import print_function
import argparse
import datetime
import os
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/calendar"]

def get_creds():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.json", "w") as token:
            token.write(creds.to_json())
    return creds

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
    parser = argparse.ArgumentParser(description="Check freebusy for attendees (uses token.json)")
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

    creds = get_creds()
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
