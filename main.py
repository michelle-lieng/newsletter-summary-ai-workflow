import os
import logging
from typing import Optional, List, Dict, Any
import google.generativeai as genai
from dotenv import load_dotenv
import os

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import re
from bs4 import BeautifulSoup, Comment

import numpy as np
from sentence_transformers import SentenceTransformer

import base64
from datetime import datetime

from urllib.parse import unquote

load_dotenv()

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


def _real_url(href: str) -> str:
    """Decode tracking links and return the first http(s) URL."""
    s = unquote(href or "")
    m = re.search(r"(https?://[^\s\"'<>]+)", s)
    return m.group(1) if m else (href or "")

def _norm_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\xa0", " ")).strip()

def chunk_text_blocks(html: str, email_subject: str, email_sender):
    """
    Returns a list of dicts:
      [{ "heading": str|None, "content": str, "links": [str, ...] }, ...]
    """
    # Parse the ALREADY-CLEANED html (run clean_email_html first)
    soup = BeautifulSoup(html, "html.parser")

    chunks = []
    for block in soup.select("div.text-block"):
        # skip blocks that themselves contain an H1
        if block.find("h1"):
            continue

        # 1) Heading = closest previous <h1>
        h1 = block.find_previous("h1")
        heading = _norm_text(h1.get_text(" ", strip=True)) if h1 else None

        # 2) Content = text of the block
        content = _norm_text(block.get_text(" ", strip=True))
        if len(content) <=1:
            continue

        # 3) Links inside the block (order-preserving de-dup)
        links, seen = [], set()
        for a in block.find_all("a", href=True):
            url = _real_url(a["href"])
            if url and url not in seen:
                seen.add(url)
                links.append(url)

        chunks.append({
            "email_sender": email_sender,
            "email_subject": email_subject,
            "heading": heading,
            "content": content,
            "links": links})

    return chunks

def score_chunks_against_interests(
    chunks: List[Dict[str, Any]],
    interests: List[str],
    model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
    include_heading: bool = False,   # set True to include "heading" in text
    batch_size: int = 64,
) -> List[Dict[str, Any]]:
    """
    For each chunk, compute cosine similarity to EACH interest.
    Returns the original chunk fields plus:
      - scores: {interest -> score}
      - best_interest, best_score
    """
    interests_clean = [s.strip() for s in interests if str(s).strip()]
    if not interests_clean:
        raise ValueError("interests list is empty.")

    # Build the text to score per chunk
    texts = []
    for ch in chunks:
        parts = []
        if include_heading and ch.get("heading"):
            parts.append(str(ch["heading"]))
        if ch.get("content"):
            parts.append(str(ch["content"]))
        texts.append(" ".join(parts).strip())

    model = SentenceTransformer(model_name)
    chunk_embs = model.encode(texts, batch_size=batch_size, normalize_embeddings=True, show_progress_bar=False)
    interest_embs = model.encode(interests_clean, normalize_embeddings=True, show_progress_bar=False)

    # cosine sims = dot product because they're L2-normalized
    sims = np.asarray(chunk_embs) @ np.asarray(interest_embs).T  # [num_chunks, num_interests]

    results = []
    for i, ch in enumerate(chunks):
        per_interest = {interests_clean[j]: round(float(sims[i, j]), 4) for j in range(len(interests_clean))}
        best_j = int(np.argmax(sims[i]))
        out = {
            **ch,
            "scores": per_interest,
            "best_interest": interests_clean[best_j],
            "best_score": round(float(sims[i, best_j]), 4),
        }
        results.append(out)

    return results

def filter_scored_chunks(scored: List[Dict[str, Any]], threshold: float = 0.38) -> List[Dict[str, Any]]:
    """Optional: keep only chunks whose best_score >= threshold."""
    return [c for c in scored if c.get("best_score", 0.0) >= threshold]

def generate_summary(chunks: List[Dict]) -> str:
    content = []
    for chunk in chunks:
        content.append(chunk["content"])
    
    # Configure Gemini with your API key
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])

    # Create a model with system instructions and generation config
    model = genai.GenerativeModel(
        model_name="gemini-2.0-flash",
        system_instruction=f"""
        You are a helpful newsletter summariser. This is content
        that is related to the users interests: 
        <{content}>
        You are educational and you do not add any additional information.
        """,
        generation_config={
            "max_output_tokens": 1000,   # cap response length (~words×4 = tokens)
            "temperature": 0.2,        # creativity
            #"top_p": 0.9,              # nucleus sampling
            #"top_k": 40                # top-k sampling
        }
    )

    # Generate a response with the user prompt
    resp = model.generate_content("Summarize the findings into a straightforward and easy to read format.")
    return resp.text

if __name__ == "__main__":
    # Basic logging setup; change to DEBUG for more verbosity
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    ########### STEP 1: Log into gmail and get read access (shown by scope)
    service = get_gmail_service(port=8002)

    ############ STEP 2: Given the newspapers in the config.yaml then extract those newspapers
    query = build_query("dan@tldrnewsletter.com","TLDR AI","4d")
    print(query)
    message_ids = list_message_ids(service, query)
    all_chunks = []
    for message_id in message_ids:
        print(message_id)
        payload = extract_messages(message_id).get("payload", {})
        from pprint import pprint
        #pprint(payload)
        headers = payload.get("headers", [])
        # #print(headers)
        subject = _header(headers, "Subject", "(no subject)")
        from_ = _header(headers, "From", "")
        #date_raw = _header(headers, "Date", "")
        # print(subject, from_, date_raw)
        # try:
        #     date = str(datetime.strptime(date_raw[:31], "%a, %d %b %Y %H:%M"))
        # except Exception:
        #     date = date_raw or ""
        # print(date)
        text = _extract_text(payload)
        print(text)
        cleaned = clean_email_html(text)
        #print(cleaned)
        chunks = chunk_text_blocks(cleaned, subject, from_)
        all_chunks += chunks
        #pprint(chunks, sort_dicts=False)
        
    interests = ["notebookLLM", "LangGraph", "Claude Code"]
    scored = score_chunks_against_interests(all_chunks, interests)
    #pprint(scored, sort_dicts=False)

    kept_chunks = filter_scored_chunks(scored)
    pprint(kept_chunks, sort_dicts=False)

    summary = generate_summary(kept_chunks)
    print(summary)
