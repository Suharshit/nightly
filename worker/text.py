"""HTML to plain text, and location rules (India / remote)."""

import html
import re
from html.parser import HTMLParser

_BLOCK_TAGS = {"p", "br", "li", "div", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "ul", "ol"}


class _Stripper(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        self.parts.append(data)


def html_to_text(raw: str | None) -> str:
    """Strip tags. Greenhouse sends entity-encoded HTML (&lt;p&gt;), so unescape first."""
    if not raw:
        return ""
    if "&lt;" in raw:
        raw = html.unescape(raw)
    p = _Stripper()
    p.feed(raw)
    text = "".join(p.parts).replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s*\n\s*", "\n", text)
    return text.strip()


# Aliases → canonical city name.
CITY_ALIASES = {
    "bengaluru": "Bengaluru", "bangalore": "Bengaluru",
    "gurugram": "Gurugram", "gurgaon": "Gurugram",
    "mumbai": "Mumbai", "bombay": "Mumbai", "navi mumbai": "Mumbai",
    "delhi": "Delhi", "new delhi": "Delhi", "noida": "Noida",
    "hyderabad": "Hyderabad", "pune": "Pune", "chennai": "Chennai",
    "kolkata": "Kolkata", "ahmedabad": "Ahmedabad", "jaipur": "Jaipur",
    "kochi": "Kochi", "cochin": "Kochi", "chandigarh": "Chandigarh",
    "indore": "Indore", "coimbatore": "Coimbatore", "thiruvananthapuram": "Thiruvananthapuram",
    "trivandrum": "Thiruvananthapuram", "mohali": "Mohali", "lucknow": "Lucknow",
    "bhubaneswar": "Bhubaneswar", "vadodara": "Vadodara", "surat": "Surat", "nagpur": "Nagpur",
    "goa": "Goa", "mysuru": "Mysuru", "mysore": "Mysuru", "visakhapatnam": "Visakhapatnam",
}
INDIA_WORDS = ("india", "karnataka", "maharashtra", "tamil nadu", "telangana", "haryana",
               "kerala", "gujarat", "west bengal", "uttar pradesh", "rajasthan", "punjab")
# A remote role with no India mention counts only if its location is made of these words alone,
# e.g. "Remote", "Remote, Global", "Anywhere", "Remote - APAC". Anything else (a US state,
# "EMEA", a foreign city) is treated as not open to someone in India. Precision over recall.
OPEN_WORDS = {"remote", "hybrid", "global", "anywhere", "worldwide", "apac", "apj", "asia",
              "asia pacific", "work from home", "wfh", "distributed", "fully remote",
              "remote first", "remote friendly"}
INDIA_CODES = {"IN", "IND", "INDIA"}
_SPLIT = re.compile(r"[,;/|()\-–•:]+|\bor\b|\band\b")


def find_city(location: str | None) -> str | None:
    if not location:
        return None
    low = location.lower()
    # Prefer two-word aliases (navi mumbai, new delhi) by checking longest first.
    for alias in sorted(CITY_ALIASES, key=len, reverse=True):
        if re.search(rf"\b{re.escape(alias)}\b", low):
            return CITY_ALIASES[alias]
    return None


def mentions_india(location: str | None) -> bool:
    if not location:
        return False
    low = location.lower()
    return find_city(location) is not None or any(
        re.search(rf"\b{w}\b", low) for w in INDIA_WORDS)


def open_location(location: str | None) -> bool:
    """True if the location names no place, only generic remote words."""
    if not location or not location.strip():
        return True
    parts = [p.strip() for p in _SPLIT.split(location.lower())]
    return all(not p or p in OPEN_WORDS for p in parts)


def india_ok(locations: list[str | None], remote: bool, country: str | None = None) -> bool:
    """Located in India, or remote with no place named other than generic remote words."""
    if any(mentions_india(loc) for loc in locations):
        return True
    if country:
        return country.strip().upper() in INDIA_CODES
    return remote and all(open_location(loc) for loc in locations)
