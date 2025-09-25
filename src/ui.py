# src/ui.py
import streamlit as st
import datetime
import json
import re
from zoneinfo import ZoneInfo

# Reuse functions from agent.py and find_slot_and_create.py (make sure running from project root)
from agent import parse_request
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

st.set_page_config(page_title="AI Meeting Scheduler", page_icon="📅", layout="centered")
st.title("📅 AI Meeting Scheduler")
st.write("Schedule a meeting with anyone in one click")

# Input box
user_input = st.text_area(
    "Your request",
    height=120,
    placeholder="e.g. Schedule a 30 minute meeting with alice@example.com tomorrow morning about the project."
)

# Helpers
def is_valid_email(e: str) -> bool:
    return bool(re.match(r"^[^@]+@[^@]+\.[^@]+$", e.strip()))

def make_description(topic: str, duration: int, attendees_display: str) -> str:
    """Short sanitized description (no raw user prompt)."""
    return f"Scheduled by AI Meeting Agent.\nTopic: {topic}\nDuration: {duration} minutes\nAttendees: {attendees_display}"

def slot_conflicts(service, emails, start_dt_utc, end_dt_utc):
    """Return (True, details) if any attendee calendar reports busy during the window."""
    items = [{"id": e} for e in emails] if emails else [
        {"id": service.calendarList().get(calendarId="primary").execute().get("id")}
    ]
    body = {
        "timeMin": start_dt_utc.isoformat(),
        "timeMax": end_dt_utc.isoformat(),
        "timeZone": "UTC",
        "items": items
    }
    resp = service.freebusy().query(body=body).execute()
    calendars_resp = resp.get("calendars", {})
    for cal in calendars_resp.values():
        if cal.get("busy"):
            return True, calendars_resp
    return False, calendars_resp

# Action
if st.button("Schedule Meeting"):
    if not user_input.strip():
        st.error("Please enter a request first.")
        st.stop()

    with st.spinner("Parsing request..."):
        try:
            parsed = parse_request(user_input)
        except Exception as e:
            st.error(f"Parsing failed: {e}")
            st.stop()

    # Show a concise summary and hide the raw JSON by default
    st.subheader("Parsed Request (summary)")
    attendees_list = parsed.get("attendees") or []
    st.markdown(f"**Attendees:** {', '.join(attendees_list) if attendees_list else 'None detected'}")
    st.markdown(f"**Topic:** {parsed.get('topic') or '—'}")
    st.markdown(f"**Time frame:** {parsed.get('time_frame') or '—'}")
    st.markdown(f"**Duration (min):** {parsed.get('duration_minutes') or 60}")
    st.markdown(f"**Preferred times:** {parsed.get('preferred_times') or 'none'}")

    # Extract parsed fields
    attendees_parsed = parsed.get("attendees") or []
    topic = parsed.get("topic") or "Meeting"
    time_frame = parsed.get("time_frame") or "next week"
    duration = int(parsed.get("duration_minutes") or 60)
    preferred = parsed.get("preferred_times") or "none"

    # Separate emails and names; require explicit emails for invite sending
    emails = [a.strip() for a in attendees_parsed if "@" in str(a)]
    names = [a for a in attendees_parsed if "@" not in str(a)]

    if not emails:
        st.error("No email found in request — please include attendee email(s). The agent requires explicit emails to send invites.")
        st.stop()

    # Basic email validation
    invalid = [e for e in emails if not is_valid_email(e)]
    if invalid:
        st.error("Parsed attendee emails contain invalid entries: " + ", ".join(invalid))
        st.stop()

    # Authenticate with Google Calendar (env-first)
    try:
        SCOPES = ["https://www.googleapis.com/auth/calendar"]
        creds = get_creds_from_env_or_local(SCOPES)
        from googleapiclient.discovery import build
        service = build("calendar", "v3", credentials=creds)
    except Exception as e:
        st.error(f"Failed to authenticate with Google Calendar: {e}")
        st.stop()

    # Get user's timezone from primary calendar
    try:
        cal_meta = service.calendars().get(calendarId="primary").execute()
        tz = cal_meta.get("timeZone", "UTC")
        user_tz = ZoneInfo(tz)
    except Exception as e:
        st.error(f"Failed to get calendar metadata: {e}")
        st.stop()

    # Parse the time window
    start_dt_local, end_dt_local = parse_time_frame(time_frame, user_tz)
    if (end_dt_local - start_dt_local).days < 1:
        end_dt_local = start_dt_local + datetime.timedelta(days=7)

    fb_start = start_dt_local.astimezone(ZoneInfo("UTC"))
    fb_end = end_dt_local.astimezone(ZoneInfo("UTC"))

    st.info(f"Checking availability from {fb_start.isoformat()} to {fb_end.isoformat()} (UTC)...")

    # Query freebusy for the parsed emails
    try:
        calendars = query_freebusy(service, emails, fb_start, fb_end)
    except Exception as e:
        st.error(f"Free/busy query failed: {e}")
        st.stop()

    merged_busy = merge_busy_intervals(calendars)

    # Build candidate free windows in preferred hours
    candidate_free = []
    day_cursor = start_dt_local.date()
    while datetime.datetime.combine(day_cursor, datetime.time(0, 0), tzinfo=user_tz) < end_dt_local:
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
        day_cursor = day_cursor + datetime.timedelta(days=1)

    candidate_free.sort(key=lambda x: x[0])
    slot_start_utc, slot_end_utc = find_first_slot(candidate_free, duration)

    if not slot_start_utc:
        st.error("❌ No available slot found in the requested window & preferred times.")
        st.stop()

    # Final pre-create conflict check
    conflict, busy_details = slot_conflicts(service, emails, slot_start_utc, slot_end_utc)
    if conflict:
        st.error("❌ Cannot create event: one or more attendees are busy during the chosen slot.")
        with st.expander("See busy slots (raw)"):
            st.write(busy_details)
        st.stop()

    # Create event with sanitized description
    attendees_display = ", ".join(emails)
    description = make_description(topic, duration, attendees_display)

    try:
        slot_start_local = slot_start_utc.astimezone(user_tz)
        slot_end_local = slot_end_utc.astimezone(user_tz)
        created = create_event(service, topic, slot_start_local, slot_end_local, emails, description=description)
    except Exception as e:
        st.error(f"Event creation failed: {e}")
        st.stop()

    st.success("✅ Meeting scheduled successfully!")
    st.markdown(f"**Title:** {topic}")
    st.markdown(f"**Time:** {slot_start_local.strftime('%a, %d %b %Y, %I:%M %p')} → {slot_end_local.strftime('%I:%M %p')} ({tz})")
    st.markdown(f"**Attendees (invites sent):** {attendees_display}")
    if created.get("htmlLink"):
        st.markdown(f"[📅 View in Google Calendar]({created['htmlLink']})")
