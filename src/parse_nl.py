# src/parse_nl.py
import os
import json
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise SystemExit("Missing OPENAI_API_KEY in .env")

client = OpenAI(api_key=OPENAI_API_KEY)

# Structured schema we want back
SCHEMA_EXAMPLE = {
    "attendees": ["First Last", "..."],
    "topic": "short summary of meeting topic",
    "time_frame": "e.g. next week / 2025-09-30 to 2025-10-02 / tomorrow afternoon",
    "duration_minutes": 60,
    "preferred_times": "mornings / afternoons / evenings / none",
    "location": "online / Zoom / physical address or null",
    "raw": "original user text"
}

SYSTEM_PROMPT = """
You are a helpful assistant that extracts scheduling information from a user's natural language request.
Return ONLY a JSON object that matches the schema exactly (no extra commentary).
Fields:
 - attendees: list of person names (strings). If none found, return [].
 - topic: short phrase for meeting subject, or null.
 - time_frame: free-text description of the requested time window (e.g., "next week", "2025-10-01 to 2025-10-03", "tomorrow afternoon"), or null.
 - duration_minutes: integer minutes (default to 60 if unspecified).
 - preferred_times: "mornings", "afternoons", "evenings", or "none".
 - location: string or null (e.g., "Zoom", "Room 401", or null).
 - raw: the original user request.
If you cannot determine a value, use null (or [] for attendees).
Be conservative: prefer null than hallucinated emails or times.
"""

def parse_request(user_text: str):
    prompt = SYSTEM_PROMPT + "\n\nUser request:\n" + user_text + "\n\nReturn the JSON now."
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=400
        )
        content = resp.choices[0].message.content.strip()
    except Exception as e:
        raise RuntimeError(f"OpenAI API error: {e}")

    # try to parse JSON from response safely
    try:
        parsed = json.loads(content)
    except Exception:
        # fallback: try to extract JSON substring
        start = content.find("{")
        end = content.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                parsed = json.loads(content[start:end+1])
            except Exception as e:
                raise RuntimeError("Failed to parse JSON from model response. Raw response:\n" + content)
        else:
            raise RuntimeError("Model did not return JSON. Raw response:\n" + content)

    # Normalize: ensure keys exist and types are correct
    out = {
        "attendees": parsed.get("attendees") or [],
        "topic": parsed.get("topic") or None,
        "time_frame": parsed.get("time_frame") or None,
        "duration_minutes": parsed.get("duration_minutes") or None,
        "preferred_times": parsed.get("preferred_times") or "none",
        "location": parsed.get("location") or None,
        "raw": user_text
    }

    # If duration null, default to 60
    if out["duration_minutes"] is None:
        out["duration_minutes"] = 60

    # normalize attendee names to simple strings
    out["attendees"] = [str(x).strip() for x in out["attendees"]]

    return out

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Parse a meeting request into structured JSON")
    parser.add_argument("text", nargs="?", help="Meeting request text (in quotes). If omitted, runs an interactive prompt.")
    args = parser.parse_args()

    if args.text:
        user_text = args.text
        result = parse_request(user_text)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    # interactive
    print("Enter meeting request (empty line to quit):")
    while True:
        try:
            user_text = input("> ").strip()
        except EOFError:
            break
        if not user_text:
            break
        try:
            result = parse_request(user_text)
            print(json.dumps(result, indent=2, ensure_ascii=False))
        except Exception as e:
            print("Error:", e)

if __name__ == "__main__":
    main()
