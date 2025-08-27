
import os
import logging
import re
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from email.message import EmailMessage
import base64
from typing import List
import logging

class Gmail():
    def __init__(self, 
                 token_file: str = "token.json",
                 credentials_file: str = "credentials.json",
                 port: int = 8002, 
                 scopes: list = ["https://www.googleapis.com/auth/gmail.readonly",
                                 "https://www.googleapis.com/auth/gmail.send"],                
                ):
        self.port = port
        self.scopes = scopes
        self.token_file = token_file
        self.credentials_file = credentials_file

    def get_gmail_service(self):
        """
        Return an authenticated Gmail API service client.
        """
        
        creds = None
        # The file token.json stores the user's access and refresh tokens, and is
        # created automatically when the authorization flow completes for the first time.
        if os.path.exists(self.token_file):
            creds = Credentials.from_authorized_user_file(self.token_file, self.scopes)

        # If there are no (valid) credentials available, let the user log in.
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_file, self.scopes
                )
                creds = flow.run_local_server(port=self.port, prompt='consent') 
                # add prompt = consent to force field "refresh_token" in token.json
            # Save the credentials for the next run
            with open(self.token_file, "w") as token:
                token.write(creds.to_json())

        try:
            # Call the Gmail API
            service = build("gmail", "v1", credentials=creds)
            logging.info("Signed into Gmail successfully.")
            return service
        except Exception as e:
            raise RuntimeError(f"Failed to build Gmail service: {e}") from e
    
    @staticmethod
    def build_query(email: str, newsletter_name: str, newer_than: str) -> str:
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

    @staticmethod
    def list_message_ids(service, query: str, max_results: int = 100) -> List[str]:
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
            logging.info("No messages found.")

        for message in messages:
            message_ids.append(message["id"])
        return message_ids

    @staticmethod
    def extract_messages(service, message_id: str):
        msg = (service.users().messages().get(userId="me", 
                                            id=message_id,
                                            format="full").execute())
        return msg
    
    @staticmethod
    def send_email(service, sender, to, subject, body_text):
        try:
            # Create the email
            message = EmailMessage()
            message.set_content(body_text)
            message["To"] = to
            message["From"] = sender
            message["Subject"] = subject

            # Encode as base64url
            encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
            create_message = {"raw": encoded_message}

            # Send
            send_message = service.users().messages().send(userId="me", body=create_message).execute()
            logging.info(f"Message sent! ID: {send_message['id']}")
            return send_message['id']
        except Exception as e:
            logging.error(f"Failed to send email: {e}")
            raise
