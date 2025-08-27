import re
from bs4 import BeautifulSoup
from urllib.parse import unquote

class Chunker():
    @staticmethod
    def _real_url(href: str) -> str:
        """Decode tracking links and return the real http(s) URL inside them."""
        s = unquote(href)
        
        # Find all possible http(s) urls in the string
        urls = re.findall(r"https?://[^\s\"'<>]+", s)
        if not urls:
            return href
        
        # If there are multiple, often the last one is the true destination
        return urls[-1]
    
    @staticmethod
    def _norm_text(text: str) -> str:
        return re.sub(r"\s+", " ", (text or "").replace("\xa0", " ")).strip()

    def chunk_text_blocks(self, html: str, email_subject: str, email_sender):
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
            heading = self._norm_text(h1.get_text(" ", strip=True)) if h1 else None

            # 2) Content = text of the block
            content = self._norm_text(block.get_text(" ", strip=True))
            if len(content) <=1:
                continue

            # 3) Links inside the block (order-preserving de-dup)
            links, seen = [], set()
            for a in block.find_all("a", href=True):
                url = self._real_url(a["href"])
                print(a["href"])
                print(url)
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
