# src/agent.py
import os
import json
import sys
from dotenv import load_dotenv
from openai import OpenAI
from zoneinfo import ZoneInfo
import datetime

# Reuse functions from find_slot_and_create
from find_slot_and_create import (
    parse_time_frame,
    preferred_hours_to_windows,
    query_freebusy,
    merge_busy_intervals,
    invert_busy_to_free,
    find_first_slot,
    create_event,
)
from google_auth_helpers import get_creds_from_env_or_local

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise SystemExit("Missing OPENAI_API_KEY in environment variables")

client = OpenAI(api_key=OPENAI_API_KEY)

SYSTEM_PROMPT = """
You are a helpful assistant that extracts scheduling information from a user's natural language request.
Return ONLY a JSON object with these fields:
- attendees: list of names or emails (strings). If no emails, user may have provided names only.
- topic: short phrase for meeting subject, or null
- time_frame: description of requested time (e.g., "next week", "tomorrow afternoon"), or null
- duration_minutes: integer minutes (default 60)
- preferred_times: "mornings", "afternoons", "evenings", or "none"
- location: string or null
- raw: the original request
"""

def parse_request(text: str):
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": SYSTEM_PROMPT + "\n\n" + text}],
        temperature=0.0,
        max_tokens=400
    )
    content = resp.choices[0].message.content.strip()
    try:
        parsed = json.loads(content)
    except Exception:
        start, end = content.find("{"), content.rfind("}")
        if start != -1 and end != -1:
            parsed = json.loads(content[start:end+1])
        else:
            raise RuntimeError("Model did not return JSON:\n" + content)
    if not parsed.get("duration_minutes"):
        parsed["duration_minutes"] = 60
    parsed["raw"] = text
    return parsed

def split_attendees_into_emails(attendees_list):
    """
    Given a list of strings (names or emails), return two lists:
    - emails: only strings that appear to be emails (contain '@')
    - names: strings that did not contain '@'
    """
    emails = []
    names = []
    for a in attendees_list:
        s = str(a).strip()
        if "@" in s:
            emails.append(s)
        elif s:
            names.append(s)
    return emails, names

def main():
    if len(sys.argv) < 2:
        print("Usage: python src/agent.py \"Schedule meeting ...\"")
        return

    user_text = " ".join(sys.argv[1:])  # allow multi-word args without shell quoting issues
    print("User request:", user_text)

    # Step 1: Parse request
    parsed = parse_request(user_text)
    print("\nParsed request:")
    print(json.dumps(parsed, indent=2))

    attendees_parsed = parsed.get("attendees") or []
    topic = parsed.get("topic") or "Meeting"
    time_frame = parsed.get("time_frame") or "next week"
    duration = int(parsed.get("duration_minutes") or 60)
    preferred = parsed.get("preferred_times") or "none"

    # Separate emails vs names
    attendee_emails, attendee_names = split_attendees_into_emails(attendees_parsed)

    if attendee_names and not attendee_emails:
        print("\n⚠️  Parsed attendees appear to be NAMES (no emails found).")
        print("   Attendee names:", ", ".join(attendee_names))
        print("   The agent will schedule the meeting on YOUR calendar only (no invites will be sent).")
        print("   To send invites, include attendee emails in your request (e.g., 'with alice@example.com').")
    elif attendee_emails:
        print("\nDetected attendee emails:", ", ".join(attendee_emails))
        if attendee_names:
            print("Also found names (not used as emails):", ", ".join(attendee_names))

    # Step 2: Setup Google Calendar service
    try:
        SCOPES = ["https://www.googleapis.com/auth/calendar"]
        creds = get_creds_from_env_or_local(SCOPES)
        from googleapiclient.discovery import build
        service = build("calendar", "v3", credentials=creds)
    except Exception as e:
        print(f"\n❌ Failed to authenticate with Google Calendar: {e}")
        return

    try:
        cal_meta = service.calendars().get(calendarId="primary").execute()
        tz = cal_meta.get("timeZone", "UTC")
        user_tz = ZoneInfo(tz)
    except Exception as e:
        print(f"\n❌ Failed to get calendar metadata: {e}")
        return

    # Step 3: Parse time window
    start_dt_local, end_dt_local = parse_time_frame(time_frame, user_tz)
    fb_start = start_dt_local.astimezone(ZoneInfo("UTC"))
    fb_end = end_dt_local.astimezone(ZoneInfo("UTC"))

    # For freebusy, query only emails if we have them, else just your primary calendar
    freebusy_emails = attendee_emails if attendee_emails else [
        service.calendarList().get(calendarId='primary').execute().get('id')
    ]

    # Step 4: Query freebusy
    calendars = query_freebusy(service, freebusy_emails, fb_start, fb_end)
    merged_busy = merge_busy_intervals(calendars)

    # Step 5: Build candidate free windows
    candidate_free = []
    day_cursor = start_dt_local.date()
    while datetime.datetime.combine(day_cursor, datetime.time(0,0), tzinfo=user_tz) < end_dt_local:
        windows = preferred_hours_to_windows(preferred, day_cursor, user_tz)
        for w_start, w_end in windows:
            w_start_clamped = max(w_start, start_dt_local)
            w_end_clamped = min(w_end, end_dt_local)
            if w_end_clamped <= w_start_clamped:
                continue
            w_start_utc = w_start_clamped.astimezone(ZoneInfo("UTC"))
            w_end_utc = w_end_clamped.astimezone(ZoneInfo("UTC"))
            free_slices = invert_busy_to_free(merged_busy, w_start_utc, w_end_utc)
            candidate_free.extend(free_slices)
        day_cursor += datetime.timedelta(days=1)

    candidate_free.sort(key=lambda x: x[0])

    slot_start_utc, slot_end_utc = find_first_slot(candidate_free, duration)
    if not slot_start_utc:
        print("\n❌ No available slot found in requested window.")
        return

    slot_start_local = slot_start_utc.astimezone(user_tz)
    slot_end_local = slot_end_utc.astimezone(user_tz)

    # Step 6: Create event
    create_attendees = attendee_emails if attendee_emails else []
    sanitized = f"Scheduled by AI Meeting Agent.\nTopic: {topic}\nDuration: {duration} minutes"
    created = create_event(service, topic, slot_start_local, slot_end_local,
                           create_attendees,
                           description=sanitized)
  
    print("\n✅ Meeting scheduled")
    print(f"Title: {topic}")
    print(f"Time: {slot_start_local.strftime('%a, %d %b %Y, %I:%M %p')} -> {slot_end_local.strftime('%I:%M %p')} ({tz})")
    if attendee_emails:
        print("Attendees (invites sent):", ", ".join(attendee_emails))
    else:
        print("No attendee emails provided — event created on your calendar only.")
    if created.get("htmlLink"):
        print("Link:", created["htmlLink"])

if __name__ == "__main__":
    main()
