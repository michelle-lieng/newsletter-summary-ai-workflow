import os
import logging
from typing import Optional, List, Dict, Any

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import re
from bs4 import BeautifulSoup, Comment
import base64
from datetime import datetime

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

def build_query(email: str, 
                newsletter_name: str,
                newer_than: str) -> str:
    """
    Creates something e.g. like
    in:inbox newer_than:"2d" from:"dan@tldrnewsletter.com" from:"TLDR AI" 
    which can filter down your gmail inbox.

    Check here for the formats allowed
    https://support.google.com/mail/answer/7190?hl=en&co=GENIE.Platform%3DAndroid
    
    For newer_than can do:
    "Search for emails newer than a time period. 
    Use d (day), m (month), or y (year)."
    """
    newer_than = newer_than.strip().lower()

    # check if newer_than in correct format
    if not re.fullmatch(r"\d+[dmy]", newer_than):
        raise ValueError("newer_than must be a number followed by 'd', 'm', or 'y' (e.g., 4d, 9m, 1y).")

    return f'in:inbox from:"{email}" from:"{newsletter_name}" newer_than:{newer_than}'

def list_message_ids(service, 
                     query: str, 
                     max_results: int = 100) -> List[str]:
    """
    Get all newsletter message ids.
    Check here: https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/list
    """
    message_ids = []

    results = (service.users().messages().list(userId="me", 
                                               q=query,
                                               maxResults=max_results).execute())
    messages = results.get("messages", [])

    if not messages:
        print("No messages found.")

    for message in messages:
        message_ids.append(message["id"])
    return message_ids

def extract_messages(message_id: str):
    msg = (service.users().messages().get(userId="me", 
                                          id=message_id,
                                          format="full").execute())
    return msg

def _header(headers: List[Dict[str,str]], name: str, default: str="") -> str:
    return next(
        (h["value"] for h in headers if h.get("name").lower()==name.lower())
        , default)
  
def _decode_body(data_b64url: str) -> str:
    return base64.urlsafe_b64decode(data_b64url.encode("utf-8")).decode("utf-8", errors="ignore")

def _extract_text(payload: Dict[str,Any]) -> str:
    """
    Prefer text/html -> strip tags; else text/plain.
    Walks nested parts.
    """
    parts = payload.get("parts", [])
    for part in parts:
        data = part.get("body").get("data")
        mime = part.get("mimeType")

        if mime == "text/html":
            raw = _decode_body(data)
            return raw.strip()
        # if mime == "text/plain":
        #     raw = _decode_body(data)
        #     soup = BeautifulSoup(raw, 'html.parser')
        #     return soup.get_text()
        
        # fall back get mimeType = "text/plain"
        # NOTE TO SELF: Figure out later
        # elif mime == "text/plain":
        #     raw = _decode_body(data)
        #     return raw.strip()

def clean_email_html(html: str) -> str:
    selectors_to_unwrap = [
        'table', 'thead', 'tbody', 'tr', 'td', 'th',
        'br', 'strong'
    ]
    selectors_to_drop = [
        'style', 'script', 'meta', 'link', 'head', 'img'
    ]

    # Hidden/preheader detection
    HIDDEN_ATTR_SELECTORS = ['[hidden]', '[aria-hidden="true"]']
    HIDDEN_STYLE_HINTS = (
        'display:none', 'visibility:hidden', 'opacity:0',
        'max-height:0', 'maxheight:0', 'height:0', 'width:0',
        'font-size:0', 'line-height:0'
    )
    def _is_hidden_inline(style: str) -> bool:
        s = (style or '').lower().replace(' ', '')
        return any(hint in s for hint in HIDDEN_STYLE_HINTS)

    soup = BeautifulSoup(html, 'html5lib')  # robust for messy email HTML

    # 0) remove comments
    for c in soup.find_all(string=lambda s: isinstance(s, Comment)):
        c.extract()

    # 1) drop hidden nodes (preheaders, visually-hidden blocks)
    for sel in HIDDEN_ATTR_SELECTORS:
        for el in soup.select(sel):
            el.decompose()
    for el in list(soup.find_all(style=True)):
        if _is_hidden_inline(el.get('style', '')):
            el.decompose()
    # also strip zero-width chars often used to pad preheaders
    for t in soup.find_all(string=True):
        cleaned = re.sub(r'[\u200B-\u200D\uFEFF]', '', t)
        if cleaned != t:
            t.replace_with(cleaned)

    # 2) unwrap = remove tag but keep its inner content
    for sel in selectors_to_unwrap:
        for el in soup.select(sel):
            el.unwrap()

    # 3) decompose = remove tag and all its children
    for sel in selectors_to_drop:
        for el in soup.select(sel):
            el.decompose()

    # 4) return only body inner HTML (avoid <html><body> wrappers)
    return soup.body.decode_contents() if soup.body else str(soup)

if __name__ == "__main__":
    # Basic logging setup; change to DEBUG for more verbosity
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    ########### STEP 1: Log into gmail and get read access (shown by scope)
    service = get_gmail_service(port=8002)

    ############ STEP 2: Given the newspapers in the config.yaml then extract those newspapers
    query = build_query("dan@tldrnewsletter.com","TLDR AI","2d")
    print(query)
    message_ids = list_message_ids(service, query)
    for message_id in message_ids:
        print(message_id)
        payload = extract_messages(message_id).get("payload", {})
        from pprint import pprint
        #pprint(payload)
        # headers = payload.get("headers", [])
        # #print(headers)
        # subject = _header(headers, "Subject", "(no subject)")
        # from_ = _header(headers, "From", "")
        # date_raw = _header(headers, "Date", "")
        # print(subject, from_, date_raw)
        # try:
        #     date = str(datetime.strptime(date_raw[:31], "%a, %d %b %Y %H:%M"))
        # except Exception:
        #     date = date_raw or ""
        # print(date)
        text = _extract_text(payload)
        #print(text)
        cleaned = clean_email_html(text)
        #print(cleaned)
