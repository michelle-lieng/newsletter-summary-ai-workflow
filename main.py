import os
import logging
from typing import Optional, List

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

import re

def get_gmail_service(
    port: int = 8002,
    credentials_path: str = "credentials.json",
    token_path: str = "token.json"
):
    """
    Return an authenticated Gmail API service client.

    What this does:
      1) Tries to load an existing OAuth token from `token_path`
      2) If token is expired but refreshable, refresh it
      3) Otherwise launches a local OAuth flow (opens browser) using `credentials_path`
      4) Saves a fresh token to `token_path`
      5) Builds and returns the Gmail service

    Raises:
      FileNotFoundError: if `credentials.json` is missing and we must re-auth
      RuntimeError: for OAuth flow or service build failures
    """
    scopes = ["https://www.googleapis.com/auth/gmail.readonly"]
    creds = None

    # 1) Load cached token if present
    if os.path.exists(token_path):
        try:
            creds = Credentials.from_authorized_user_file(token_path, scopes)
            logging.info("Loaded cached OAuth token from %s", token_path)
        except Exception as e:
            logging.warning("Failed to read existing token (%s). Will re-authenticate.", e)
            creds = None

    # 2) Refresh or 3) Re-authenticate if needed
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                logging.info("Refreshed OAuth token.")
            except RefreshError as e:
                logging.warning("Refresh token invalid/revoked (%s). Re-authenticating.", e)
                creds = None  # fall through to re-auth

        if not creds:
            # Need the client secrets to run the OAuth flow
            if not os.path.exists(credentials_path):
                raise FileNotFoundError(
                    f"Missing '{credentials_path}'. "
                    "Download an OAuth 2.0 Client ID (Desktop app) from Google Cloud Console "
                    "and place it next to this script."
                )
            # Try chosen port; if busy, fall back to any free port
            try:
                flow = InstalledAppFlow.from_client_secrets_file(credentials_path, scopes)
                creds = flow.run_local_server(port=port, open_browser=True)
            except OSError as oe:
                logging.warning("Port %s unavailable (%s). Falling back to a random free port.", port, oe)
                flow = InstalledAppFlow.from_client_secrets_file(credentials_path, scopes)
                creds = flow.run_local_server(port=0, open_browser=True)
            except Exception as e:
                raise RuntimeError(f"OAuth flow failed: {e}") from e

        # 4) Persist token for next run
        try:
            with open(token_path, "w") as token:
                token.write(creds.to_json())
            logging.info("Saved new token to %s", token_path)
        except Exception as e:
            logging.error("Could not write token file '%s': %s", token_path, e)

    # 5) Build Gmail service
    try:
        service = build("gmail", "v1", credentials=creds)
        logging.info("Signed into Gmail successfully.")
        return service
    except Exception as e:
        raise RuntimeError(f"Failed to build Gmail service: {e}") from e

# ---------- Query helpers ----------
def parse_newer_than(newer_than: str) -> str:
    newer_than = newer_than.strip().lower()
    if re.fullmatch(r"\d+[dw]", newer_than): 
        return f"newer_than:{newer_than}"  # 7d / 2w
    if re.fullmatch(r"\d+", newer_than):     
        return f"newer_than:{newer_than}d" # "14" -> 14d

def build_query(email: str, 
                newsletter_name: str,
                newer_than: str) -> str:
    """
    Creates something e.g. like
    in:inbox newer_than:2d from:dan@tldrnewsletter.com from:"TLDR AI" 
    which can filter down your gmail inbox.
    """
    parts = ['in:inbox', f'from:"{email}"', f'from:"{newsletter_name}"']
    nt = parse_newer_than(newer_than)
    parts.append(nt)
    return " ".join(parts)

def list_message_ids(service, 
                     query: str, 
                     max_results: int = 50) -> List[str]:
    
    ids, page_token = [], None
    
    while True:
        resp = service.users().messages().list(
            userId="me", q=query, maxResults=min(max_results, 100), pageToken=page_token
        ).execute()
        for m in resp.get("messages", []):
            ids.append(m["id"])
            if len(ids) >= max_results:
                return ids
        page_token = resp.get("nextPageToken")
        if not page_token or len(ids) >= max_results:
            return ids

if __name__ == "__main__":
    # Basic logging setup; change to DEBUG for more verbosity
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    ########### STEP 1: Log into gmail and get read access (shown by scope)
    service = get_gmail_service(port=8002)

    ############ STEP 2: Given the newspapers in the config.yaml then extract those newspapers
    query = build_query("dan@tldrnewsletter.com","TLDR AI","2")
    print(query)
    print(list_message_ids(service, query, max_results=3))