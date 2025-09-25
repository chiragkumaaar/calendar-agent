# src/test_calendar.py
from __future__ import print_function
import datetime
import os.path
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# If modifying scopes, delete token.json
SCOPES = ["https://www.googleapis.com/auth/calendar"]

def main():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.json", "w") as token:
            token.write(creds.to_json())

    service = build("calendar", "v3", credentials=creds)

    # Call the Calendar API
    now = datetime.datetime.utcnow().isoformat() + "Z"  # 'Z' means UTC
    print("Getting the upcoming 10 events")
    events_result = service.events().list(
        calendarId="primary", timeMin=now,
        maxResults=10, singleEvents=True,
        orderBy="startTime").execute()
    events = events_result.get("items", [])

    if not events:
        print("No upcoming events found.")
    for event in events:
        start = event["start"].get("dateTime", event["start"].get("date"))
        print(start, event["summary"])

if __name__ == "__main__":
    main()
