"""Who is calling: check a Supabase access token with Supabase Auth itself.

This project signs tokens with ES256. Verifying that locally would need the
`cryptography` package (several MB), so instead we ask GET /auth/v1/user, which
validates the token and returns the user. Answers are cached per token for 5 minutes
(never past the token's own expiry), so it costs one call per session, not per request.
"""

import base64
import json
import os
import time

import httpx
from fastapi import HTTPException, Request

CACHE_SECONDS = 300


def _expiry(token: str) -> float | None:
    """The token's exp claim, read without verifying (Supabase already verified it)."""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return float(json.loads(base64.urlsafe_b64decode(payload))["exp"])
    except (IndexError, KeyError, ValueError, TypeError):
        return None


class SupabaseAuth:
    def __init__(self, url: str | None = None, anon_key: str | None = None,
                 client: httpx.Client | None = None):
        self.url = (url or os.environ["SUPABASE_URL"]).rstrip("/")
        self.key = anon_key or os.environ["SUPABASE_ANON_KEY"]
        self.client = client or httpx.Client(timeout=10)
        self.cache: dict[str, tuple[float, dict]] = {}

    def user(self, token: str) -> dict:
        now = time.time()
        hit = self.cache.get(token)
        if hit and hit[0] > now:
            return hit[1]
        r = self.client.get(f"{self.url}/auth/v1/user",
                            headers={"apikey": self.key, "Authorization": f"Bearer {token}"})
        if r.status_code in (401, 403):
            raise HTTPException(401, "Invalid or expired sign-in. Please sign in again.")
        r.raise_for_status()
        data = r.json()
        user = {"id": data["id"], "email": data.get("email")}
        until = now + CACHE_SECONDS
        exp = _expiry(token)
        if exp is not None:
            until = min(until, exp)
        if len(self.cache) > 10_000:
            self.cache.clear()
        self.cache[token] = (until, user)
        return user


def current_user(request: Request) -> dict:
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(401, "Sign in first.")
    return request.app.state.auth.user(token)
