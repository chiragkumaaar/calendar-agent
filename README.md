# 📅 AI Meeting Scheduler

An AI-powered calendar agent that parses natural language meeting requests, finds free time slots for all participants, and automatically schedules meetings in Google Calendar.

---

## 🚀 What the Agent Does
- Understands natural language requests like:
  > *"Schedule a 30-minute meeting with alice@example.com and bob@example.com next week, mornings preferred, to discuss the project."*
- Extracts key details:
  - Attendees (emails)
  - Topic / purpose
  - Duration
  - Time frame (e.g., "tomorrow", "next week")
  - Preferred times (morning / afternoon / evening)
- Finds the **first available slot** that works for all attendees using Google Calendar’s free/busy data.
- Creates the event directly in Google Calendar and sends invites to attendees.

---

## ✨ Key Features
- **Natural language understanding** → powered by OpenAI API.
- **Google Calendar integration** → checks free/busy and creates events automatically.
- **Conflict prevention** → validates that attendees are not busy before scheduling.
- **Streamlit UI** → easy-to-use interface for demo and interaction.
- **CLI mode** → for quick testing in the terminal.

---

## ⚠️ Limitations
- Requires attendees’ **email addresses** in the request.  
  > If no email is provided, the agent will **not schedule** the meeting.
- Time parsing is approximate (e.g., “morning” is mapped to 9 AM–12 PM).
- Currently supports **Google Calendar only** (no Outlook/iCal).
- Assumes all times are based on the **user’s primary calendar timezone**.

---

## 🛠️ Tools & APIs Used
- **Python 3.12+**
- [OpenAI API](https://platform.openai.com/) → natural language parsing  
- [Google Calendar API](https://developers.google.com/calendar) → event scheduling & free/busy checks  
- [Streamlit](https://streamlit.io/) → UI   

---

## ⚙️ Setup Instructions

1. Clone the repo
```bash
git clone https://github.com/chiragkumaaar/calendar-agent.git
cd calendar-agent
```
2. Create a virtual environment
 ```bash
 python -m venv venv
 source venv/bin/activate     # Mac/Linux
 venv\Scripts\activate        # Windows
```
3. Install dependencies
```bash
 pip install -r requirements.txt
 ```
4. Setup environment variables
 Create a `.env` file in the project root:
 ```env
 OPENAI_API_KEY=your_openai_api_key
```
5 Google API credentials- 
 Enable the **Google Calendar API** in [Google Cloud
 Console](https://console.cloud.google.com/).  - Download your `credentials.json` and place it in the project root.  - On first run, youll be asked to authenticate, and a `token.json` will be created (dont commit these files).
6. Run the agent
 **Streamlit UI (recommended):**
 ```bash
 streamlit run src/ui.py

**Notes on Security**
- Do **not** commit `.env`, `credentials.json`, or `token.json` to GitHub.  - Use `.env.example` to show placeholders instead.  
