# src/find_slot_and_create.py
import datetime
from zoneinfo import ZoneInfo
from googleapiclient.discovery import build
from src.google_auth_helpers import get_creds_from_env_or_local

# Scopes required for the Google Calendar API
SCOPES = ["https://www.googleapis.com/auth/calendar.events"]

def get_service():
    """
    Returns an authenticated Google Calendar API service object.
    Uses environment secrets (GOOGLE_TOKEN_JSON / GOOGLE_CREDENTIALS_JSON) if available.
    """
    creds = get_creds_from_env_or_local(SCOPES)
    return build("calendar", "v3", credentials=creds)

def parse_time_frame(time_frame: str, user_tz: ZoneInfo):
    """
    Parses a natural language time frame and returns a start and end datetime object.
    (This is a placeholder; integrate an LLM for robust parsing if desired)
    """
    today = datetime.datetime.now(user_tz)
    if "today" in time_frame.lower():
        start = today.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + datetime.timedelta(days=1)
    elif "tomorrow" in time_frame.lower():
        start = today.replace(hour=0, minute=0, second=0, microsecond=0) + datetime.timedelta(days=1)
        end = start + datetime.timedelta(days=1)
    else:  # Fallback: next 7 days
        start = today.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + datetime.timedelta(days=7)
    return start, end

def preferred_hours_to_windows(preferred_times, day_cursor, user_tz):
    """
    Converts preferred times (e.g., 'morning') into specific time windows.
    """
    windows = []
    if "morning" in preferred_times.lower():
        start_time = datetime.time(9, 0)
        end_time = datetime.time(12, 0)
        windows.append((
            datetime.datetime.combine(day_cursor, start_time, tzinfo=user_tz),
            datetime.datetime.combine(day_cursor, end_time, tzinfo=user_tz)
        ))
    elif "afternoon" in preferred_times.lower():
        start_time = datetime.time(13, 0)
        end_time = datetime.time(17, 0)
        windows.append((
            datetime.datetime.combine(day_cursor, start_time, tzinfo=user_tz),
            datetime.datetime.combine(day_cursor, end_time, tzinfo=user_tz)
        ))
    elif "evening" in preferred_times.lower():
        start_time = datetime.time(18, 0)
        end_time = datetime.time(21, 0)
        windows.append((
            datetime.datetime.combine(day_cursor, start_time, tzinfo=user_tz),
            datetime.datetime.combine(day_cursor, end_time, tzinfo=user_tz)
        ))
    else:
        # Default to full workday
        start_time = datetime.time(9, 0)
        end_time = datetime.time(17, 0)
        windows.append((
            datetime.datetime.combine(day_cursor, start_time, tzinfo=user_tz),
            datetime.datetime.combine(day_cursor, end_time, tzinfo=user_tz)
        ))
    return windows

def query_freebusy(service, emails, fb_start, fb_end):
    """
    Queries the Google Calendar API for free/busy information for a list of emails.
    """
    items = [{"id": e} for e in emails]
    body = {
        "timeMin": fb_start.isoformat(),
        "timeMax": fb_end.isoformat(),
        "timeZone": "UTC",
        "items": items,
    }
    resp = service.freebusy().query(body=body).execute()
    return resp.get("calendars", {})

def merge_busy_intervals(calendars):
    """
    Merges busy intervals from multiple calendars into a single list of non-overlapping intervals.
    """
    all_busy = []
    for cal in calendars.values():
        all_busy.extend([(b["start"], b["end"]) for b in cal.get("busy", [])])
    
    if not all_busy:
        return []

    all_busy.sort(key=lambda x: x[0])
    merged = []
    current_start, current_end = all_busy[0]

    for next_start, next_end in all_busy[1:]:
        if next_start < current_end:
            current_end = max(current_end, next_end)
        else:
            merged.append((current_start, current_end))
            current_start, current_end = next_start, next_end
    
    merged.append((current_start, current_end))
    return merged

def invert_busy_to_free(merged_busy, window_start, window_end):
    """
    Given busy intervals, find free slots within a time window.
    """
    if not merged_busy:
        return [(window_start, window_end)]

    free_slots = []
    last_end = window_start
    
    for busy_start_str, busy_end_str in merged_busy:
        busy_start = datetime.datetime.fromisoformat(busy_start_str)
        busy_end = datetime.datetime.fromisoformat(busy_end_str)
        if last_end < busy_start:
            free_slots.append((last_end, busy_start))
        last_end = max(last_end, busy_end)
    
    if last_end < window_end:
        free_slots.append((last_end, window_end))
        
    return free_slots

def find_first_slot(candidate_free, duration):
    """
    Finds the first slot from free intervals that fits the meeting duration.
    """
    duration_delta = datetime.timedelta(minutes=duration)
    for free_start, free_end in candidate_free:
        if free_end - free_start >= duration_delta:
            return free_start, free_start + duration_delta
    return None, None

def create_event(service, topic, start_dt, end_dt, attendees, description=""):
    """
    Creates a new calendar event with the given details.
    """
    event = {
        "summary": topic,
        "description": description,
        "start": {
            "dateTime": start_dt.isoformat(),
            "timeZone": str(start_dt.tzinfo) or "UTC",
        },
        "end": {
            "dateTime": end_dt.isoformat(),
            "timeZone": str(end_dt.tzinfo) or "UTC",
        },
        "attendees": [{"email": email} for email in attendees],
        "conferenceData": {
            "createRequest": {
                "requestId": f"{topic.replace(' ', '-')}-{datetime.datetime.now().isoformat()}",
                "conferenceSolutionKey": {"type": "hangoutsMeet"},
            },
        },
    }
    created_event = service.events().insert(
        calendarId="primary",
        body=event,
        sendNotifications=True,
        conferenceDataVersion=1
    ).execute()
    return created_event
