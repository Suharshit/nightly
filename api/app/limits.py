"""Cheap protection for a small free server: upload size and per-visitor request rates.

Upload size: Starlette reads a whole multipart upload (to memory or a temp file) before the
route runs, so /resume checks the declared Content-Length first and refuses large or unsized
bodies without reading them.

Rate limits: a sliding one-minute window per visitor and route group, kept in memory (the
Space runs one process). A visitor is the signed-in token when there is one, else the client
address the Hugging Face proxy reports. That address can be faked by a determined client, so
this stops casual hammering, not a real attack.
"""

import time
from collections import defaultdict, deque

from fastapi import Request
from fastapi.responses import JSONResponse

from api.app.resume import MAX_BYTES

UPLOAD_PATH = "/resume"
UPLOAD_LIMIT = MAX_BYTES + 64 * 1024       # the PDF plus multipart headers

# Requests per minute per visitor. /chat also has its own daily cap per user.
RATES = {"/matches": 60, "/resume": 5, "/chat": 20, "/feedback": 120, "/prefs": 30}
WINDOW = 60.0

_hits: dict[tuple[str, str], deque] = defaultdict(deque)


def visitor(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    if token:
        return "t:" + token[-32:]               # the token's tail is enough to tell users apart
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return "ip:" + forwarded.split(",")[-1].strip()   # the hop the proxy itself added
    return "ip:" + (request.client.host if request.client else "?")


def too_many(key: tuple[str, str], limit: int, now: float) -> float | None:
    """Seconds to wait if this request is over the limit, else None (and it is counted)."""
    hits = _hits[key]
    while hits and hits[0] <= now - WINDOW:
        hits.popleft()
    if len(hits) >= limit:
        return hits[0] + WINDOW - now
    hits.append(now)
    if len(_hits) > 50_000:                     # bound memory if many visitors pass through
        _hits.clear()
    return None


async def guard(request: Request, call_next):
    path = request.url.path
    if request.method == "POST" and path == UPLOAD_PATH:
        size = request.headers.get("content-length")
        if size is None:
            return JSONResponse({"detail": "Upload size missing."}, status_code=411)
        if not size.isdigit() or int(size) > UPLOAD_LIMIT:
            return JSONResponse({"detail": "That file is too big. The limit is 5 MB."},
                                status_code=413)
    limit = RATES.get(path)
    if limit and request.method != "OPTIONS":
        wait = too_many((visitor(request), path), limit, time.monotonic())
        if wait is not None:
            secs = max(1, int(wait + 0.999))
            return JSONResponse({"detail": f"Too many requests. Try again in {secs} s."},
                                status_code=429, headers={"Retry-After": str(secs)})
    return await call_next(request)
