# src/test_calendar.py
from __future__ import print_function
import datetime
from googleapiclient.discovery import build
from src.google_auth_helpers import get_creds_from_env_or_local

# If modifying scopes, update here
SCOPES = ["https://www.googleapis.com/auth/calendar"]

def main():
    # Authenticate with Google Calendar
    creds = get_creds_from_env_or_local(SCOPES)
    service = build("calendar", "v3", credentials=creds)

    # Call the Calendar API
    now = datetime.datetime.utcnow().isoformat() + "Z"  # 'Z' means UTC
    print("Getting the upcoming 10 events")
    events_result = service.events().list(
        calendarId="primary",
        timeMin=now,
        maxResults=10,
        singleEvents=True,
        orderBy="startTime"
    ).execute()
    events = events_result.get("items", [])

    if not events:
        print("No upcoming events found.")
    for event in events:
        start = event["start"].get("dateTime", event["start"].get("date"))
        print(start, event.get("summary", "(no title)"))

if __name__ == "__main__":
    main()
