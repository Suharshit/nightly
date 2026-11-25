"""Polite async HTTP client: at most 1 request/second per host, retries with backoff."""

import asyncio
import os
import time
from urllib.parse import urlparse

import httpx

CONTACT = os.getenv("CONTACT_EMAIL") or os.getenv("CONTACT_URL", "https://github.com/Suharshit/nightly")
USER_AGENT = f"nightly-jobs/0.1 (+{CONTACT})"


class PoliteClient:
    def __init__(self, per_host_interval: float = 1.0, retries: int = 3, timeout: float = 60):
        self.interval = per_host_interval
        self.retries = retries
        self._locks: dict[str, asyncio.Lock] = {}
        self._last: dict[str, float] = {}
        self._client = httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            timeout=timeout, follow_redirects=True,
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self._client.aclose()

    async def _wait_turn(self, host: str) -> None:
        lock = self._locks.setdefault(host, asyncio.Lock())
        async with lock:
            wait = self._last.get(host, 0) + self.interval - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            self._last[host] = time.monotonic()

    async def get_json(self, url: str):
        """Return parsed JSON, or None on 404. Raises after retries on other failures."""
        host = urlparse(url).netloc
        for attempt in range(self.retries + 1):
            await self._wait_turn(host)
            try:
                r = await self._client.get(url)
            except httpx.TransportError:
                if attempt == self.retries:
                    raise
            else:
                if r.status_code == 404:
                    return None
                if r.status_code < 400:
                    return r.json()
                if r.status_code not in (429, 500, 502, 503, 504) or attempt == self.retries:
                    r.raise_for_status()
                retry_after = r.headers.get("retry-after")
                if retry_after and retry_after.isdigit():
                    await asyncio.sleep(int(retry_after))
            await asyncio.sleep(2 ** attempt)
        return None
