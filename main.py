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
    SCOPES: list = ["https://www.googleapis.com/auth/gmail.readonly"]
):
    """
    Return an authenticated Gmail API service client.
    """
    
    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first time.
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "credentials.json", SCOPES
            )
            creds = flow.run_local_server(port=port, prompt='consent') 
            # add prompt = consent to force field "refresh_token" in token.json
        # Save the credentials for the next run
        with open("token.json", "w") as token:
            token.write(creds.to_json())

    try:
        # Call the Gmail API
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