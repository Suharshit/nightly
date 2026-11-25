"""Resume PDF -> text -> skills -> the text we embed.

Only the extracted text is stored (never the PDF), to make matches; "delete my data"
removes it with the profile.
"""

from io import BytesIO

from pypdf import PdfReader

from worker.rules import find_skills

MAX_BYTES = 5 * 1024 * 1024
MAX_PAGES = 10
MAX_CHARS = 20_000
MIN_CHARS = 200        # less than this is almost always a scanned image
EMBED_CHARS = 1500     # bge-small reads ~512 tokens; skills go first so they always count


class ResumeError(ValueError):
    """A message safe to show the user."""


def pdf_text(data: bytes) -> str:
    if len(data) > MAX_BYTES:
        raise ResumeError("That file is over 5 MB. Please upload a smaller PDF.")
    if not data.startswith(b"%PDF"):
        raise ResumeError("Please upload your resume as a PDF.")
    try:
        reader = PdfReader(BytesIO(data))
        pages = [p.extract_text() or "" for p in reader.pages[:MAX_PAGES]]
    except Exception as e:  # pypdf raises many types on broken files
        raise ResumeError("We couldn't open that PDF. Try exporting it again.") from e
    text = " ".join(" ".join(pages).split())[:MAX_CHARS]
    if len(text) < MIN_CHARS:
        raise ResumeError("We couldn't read text from that PDF. Is it a scanned image? "
                          "Please upload a text PDF.")
    return text


def resume_skills(text: str) -> list[str]:
    return find_skills("", text, limit=20)


def embed_text(skills: list[str], text: str) -> str:
    head = f"Skills: {', '.join(skills)}. " if skills else ""
    return head + text[:EMBED_CHARS]
