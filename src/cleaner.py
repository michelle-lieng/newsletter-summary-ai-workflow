from typing import List, Dict, Any
import re
from bs4 import BeautifulSoup, Comment
import base64

class Cleaner():
    @staticmethod
    def _header(headers: List[Dict[str,str]], name: str, default: str="") -> str:
        return next(
            (h["value"] for h in headers if h.get("name").lower()==name.lower())
            , default)
    
    @staticmethod
    def _decode_body(data: str) -> str:
        return base64.urlsafe_b64decode(data.encode("utf-8")).decode("utf-8", errors="ignore")

    def _extract_text(self, payload: Dict[str,Any]) -> str:
        """
        Prefer text/html -> strip tags; else text/plain.
        Walks nested parts.
        """
        parts = payload.get("parts", [])
        for part in parts:
            data = part.get("body").get("data")
            mime = part.get("mimeType")

            if mime == "text/html":
                raw = self._decode_body(data)
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

    @staticmethod
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
