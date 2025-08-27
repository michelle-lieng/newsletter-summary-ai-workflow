import os
import logging
from config import Config
from gmail import Gmail
from summariser import Summariser
from cleaner import Cleaner
from chunker import Chunker
from scorer import Scorer
from pprint import pprint

from dotenv import load_dotenv
load_dotenv()

class Main():
    # Basic logging setup; change to DEBUG for more verbosity
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    @staticmethod
    def main():
        # STEP 1: Log into gmail and get read and write access (given by scope)
        gmail = Gmail()
        service = gmail.get_gmail_service()

        # STEP 2: Get all message_ids from all newsletters given in config.yaml
        config = Config()

        all_message_ids = []
        for newsletter in config.get("newsletters", []):
            query = gmail.build_query(newsletter.get("email"),
                                    newsletter.get("name"),
                                    config.get("newer_than"))
            logging.info(f"This is the query: {query}")
            message_ids = gmail.list_message_ids(service, query)
            all_message_ids += message_ids
            
        # STEP 3: For all message_ids extract HTML, clean + chunk them
        all_chunks = []
        cleaner = Cleaner()
        chunker = Chunker()

        for message_id in all_message_ids:
            logging.info(f"This is the message_id: {message_id}")
            payload = gmail.extract_messages(service, message_id).get("payload", {})
            #pprint(payload)
            headers = payload.get("headers", [])
            # #print(headers)
            subject = cleaner._header(headers, "Subject", "(no subject)")
            from_ = cleaner._header(headers, "From", "")
            #date_raw = _header(headers, "Date", "")
            # print(subject, from_, date_raw)
            # try:
            #     date = str(datetime.strptime(date_raw[:31], "%a, %d %b %Y %H:%M"))
            # except Exception:
            #     date = date_raw or ""
            # print(date)
            text = cleaner._extract_text(payload)
            #print(text)
            cleaned = cleaner.clean_email_html(text)
            #print(cleaned)
            chunks = chunker.chunk_text_blocks(cleaned, subject, from_)
            all_chunks += chunks
            #pprint(chunks, sort_dicts=False)
        
        # STEP 4: Score the chunks based on user interests
        scorer = Scorer()
        interests = config.get("preferences").get("interests")
        scored = scorer.score_chunks_against_interests(all_chunks, interests)
        #pprint(scored, sort_dicts=False)

        kept_chunks = scorer.filter_scored_chunks(scored)
        pprint(kept_chunks, sort_dicts=False)

        # STEP 5: Use LLM to summarize the chunks
        summariser = Summariser()
        summary = summariser.generate_summary(kept_chunks)
        print(summary)

        # STEP 6: Send summary newsletter to email
        gmail.send_email(
            service,
            sender=os.getenv("EMAIL_FROM"),
            to=os.getenv("EMAIL_TO"),
            subject="Weekly Newsletter Summary",
            body_text=summary
        )

if __name__ == "__main__":
    main = Main()
    main.main()