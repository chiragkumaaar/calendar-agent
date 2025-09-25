# src/google_auth_helpers.py
import os
import json
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

def get_creds_from_env_or_local(scopes):
    """
    Return google Credentials.
    Priority:
      1) GOOGLE_TOKEN_JSON env var (recommended for cloud). Use it and refresh if needed.
      2) GOOGLE_CREDENTIALS_JSON env var: run interactive flow (works locally; not recommended on cloud).
      3) Local token.json / credentials.json files (dev).
    """
    # 1) Try token JSON from env (preferred on Render)
    token_env = os.getenv("GOOGLE_TOKEN_JSON")
    if token_env:
        try:
            token_info = json.loads(token_env)
            creds = Credentials.from_authorized_user_info(token_info, scopes)
            # refresh if expired
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
            return creds
        except Exception as e:
            # fall through to try client config
            print("Warning: failed to load/refresh GOOGLE_TOKEN_JSON:", e)

    # 2) Try client credentials in env (may require interactive flow)
    creds_env = os.getenv("GOOGLE_CREDENTIALS_JSON")
    if creds_env:
        try:
            client_config = json.loads(creds_env)
            # Run local server flow — works when running locally.
            flow = InstalledAppFlow.from_client_config(client_config, scopes=scopes)
            creds = flow.run_local_server(port=0)
            return creds
        except Exception as e:
            print("Warning: failed to run InstalledAppFlow from GOOGLE_CREDENTIALS_JSON:", e)

    # 3) Local files fallback (development)
    if os.path.exists("token.json"):
        try:
            creds = Credentials.from_authorized_user_file("token.json", scopes)
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
            return creds
        except Exception:
            pass

    if os.path.exists("credentials.json"):
        try:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", scopes=scopes)
            creds = flow.run_local_server(port=0)
            # Optionally save token.json for local dev convenience
            with open("token.json", "w", encoding="utf-8") as f:
                f.write(creds.to_json())
            return creds
        except Exception:
            pass

    raise RuntimeError(
        "Google auth not configured. Provide GOOGLE_TOKEN_JSON (recommended) or GOOGLE_CREDENTIALS_JSON or local credentials.json/token.json."
    )
