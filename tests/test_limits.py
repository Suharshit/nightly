"""Upload size guard and per-visitor rate limits (api/app/limits.py)."""

import asyncio

from starlette.requests import Request

from api.app import limits

H = {"Authorization": "Bearer good-token"}


def _request(method: str, path: str, headers: dict[str, str]) -> Request:
    scope = {"type": "http", "method": method, "path": path, "query_string": b"",
             "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
             "client": ("10.0.0.9", 1234)}
    return Request(scope)


async def _ok(request):
    return "passed"


def _guard(method, path, headers):
    return asyncio.run(limits.guard(_request(method, path, headers), _ok))


def test_upload_needs_a_size_and_must_be_small():
    assert _guard("POST", "/resume", {}).status_code == 411
    big = _guard("POST", "/resume", {"content-length": str(limits.UPLOAD_LIMIT + 1)})
    assert big.status_code == 413 and b"5 MB" in big.body
    assert _guard("POST", "/resume", {"content-length": "abc"}).status_code == 413
    assert _guard("POST", "/resume", {"content-length": "2048"}) == "passed"
    assert _guard("GET", "/me", {}) == "passed"                # other routes untouched


def test_oversized_upload_refused_through_the_app(api):
    c, _, _ = api
    r = c.post("/resume", content=b"x" * (limits.UPLOAD_LIMIT + 10),
               headers={**H, "Content-Type": "application/pdf"})
    assert r.status_code == 413


def test_rate_limit_per_visitor_with_retry_after_and_cors(api, monkeypatch):
    c, _, _ = api
    monkeypatch.setitem(limits.RATES, "/matches", 2)
    origin = {"Origin": "http://localhost:3000"}
    for _ in range(2):
        assert c.get("/matches", params={"q": ""}, headers=origin).status_code == 400
    r = c.get("/matches", params={"q": ""}, headers=origin)
    assert r.status_code == 429 and int(r.headers["retry-after"]) >= 1
    assert r.headers["access-control-allow-origin"] == "http://localhost:3000"  # readable
    # A different visitor (signed in) has its own allowance.
    assert c.get("/matches", params={"q": ""}, headers=H).status_code != 429


def test_window_slides(monkeypatch):
    key = ("ip:1.2.3.4", "/matches")
    assert limits.too_many(key, 2, 100.0) is None
    assert limits.too_many(key, 2, 110.0) is None
    assert limits.too_many(key, 2, 120.0) == 100.0 + limits.WINDOW - 120.0
    assert limits.too_many(key, 2, 100.0 + limits.WINDOW + 0.1) is None   # oldest expired


def test_visitor_key():
    assert limits.visitor(_request("GET", "/matches", H)).startswith("t:")
    fwd = {"x-forwarded-for": "6.6.6.6, 49.36.1.2"}
    assert limits.visitor(_request("GET", "/matches", fwd)) == "ip:49.36.1.2"
    assert limits.visitor(_request("GET", "/matches", {})) == "ip:10.0.0.9"
