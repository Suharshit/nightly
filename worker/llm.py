"""LLM backends for extraction: Groq (OpenAI-compatible, strict JSON schema) and Ollama.

Both take a system + user prompt and a JSON schema and return (parsed dict, usage dict).
"""

import json
import os
import time

import httpx

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


class DailyLimitReached(Exception):
    """The model's daily quota is used up; stop now and resume tomorrow."""


class RateLimiter:
    """Client-side requests/min and tokens/min budget, corrected by Groq's response headers."""

    def __init__(self, rpm: int, tpm: int):
        self.rpm, self.tpm = rpm, tpm
        self.calls: list[tuple[float, int]] = []  # (timestamp, tokens)

    def wait(self, tokens: int) -> None:
        while True:
            now = time.monotonic()
            self.calls = [(t, n) for t, n in self.calls if now - t < 60]
            used = sum(n for _, n in self.calls)
            if len(self.calls) < self.rpm and used + tokens <= self.tpm:
                self.calls.append((now, tokens))
                return
            oldest = self.calls[0][0]
            time.sleep(max(0.5, 60 - (now - oldest)))

    def correct(self, actual_tokens: int) -> None:
        if self.calls:
            t, _ = self.calls[-1]
            self.calls[-1] = (t, actual_tokens)


def _seconds(value: str | None) -> float:
    """Parse Groq reset/retry values like '7.66s', '2m59.56s' or '12'."""
    if not value:
        return 0.0
    total, num = 0.0, ""
    for ch in value:
        if ch.isdigit() or ch == ".":
            num += ch
        elif ch in "hms" and num:
            total += float(num) * {"h": 3600, "m": 60, "s": 1}[ch]
            num = ""
    return total + (float(num) if num else 0.0)


class GroqBackend:
    name = "groq"

    def __init__(self, model: str, rpm: int = 30, tpm: int = 8000, timeout: float = 60):
        self.model = model
        self.key = os.environ["GROQ_API_KEY"]
        self.limiter = RateLimiter(rpm, tpm)
        self.client = httpx.Client(timeout=timeout)

    def complete(self, system: str, user: str, schema: dict, max_tokens: int = 400):
        est = (len(system) + len(user)) // 3 + max_tokens
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "temperature": 0,
            "max_completion_tokens": max_tokens,
            "response_format": {"type": "json_schema",
                                "json_schema": {"name": "job_fields", "strict": True,
                                                "schema": schema}},
        }
        if self.model.startswith("openai/gpt-oss"):
            body["reasoning_effort"] = "low"
        for attempt in range(3):
            self.limiter.wait(est)
            r = self.client.post(GROQ_URL, json=body,
                                 headers={"Authorization": f"Bearer {self.key}"})
            if r.status_code == 429:
                wait = _seconds(r.headers.get("retry-after"))
                if wait > 120 or r.headers.get("x-ratelimit-remaining-requests") == "0":
                    raise DailyLimitReached(f"{self.model}: retry-after {wait:.0f}s")
                time.sleep(max(wait, 2 ** attempt))
                continue
            r.raise_for_status()
            data = r.json()
            usage = data.get("usage") or {}
            self.limiter.correct(usage.get("total_tokens", est))
            if r.headers.get("x-ratelimit-remaining-requests") == "0":
                raise DailyLimitReached(f"{self.model}: daily requests used")
            content = data["choices"][0]["message"]["content"]
            return json.loads(content), usage
        raise RuntimeError("groq: still rate limited after retries")


class OllamaBackend:
    name = "ollama"

    def __init__(self, model: str, url: str | None = None, timeout: float = 600):
        self.model = model
        self.url = (url or os.getenv("OLLAMA_URL", "http://localhost:11434")).rstrip("/")
        self.client = httpx.Client(timeout=timeout)

    def complete(self, system: str, user: str, schema: dict, max_tokens: int = 400):
        r = self.client.post(f"{self.url}/api/chat", json={
            "model": self.model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "format": schema,
            "stream": False,
            "options": {"temperature": 0, "num_predict": max_tokens, "num_ctx": 4096},
        })
        r.raise_for_status()
        data = r.json()
        usage = {"prompt_tokens": data.get("prompt_eval_count", 0),
                 "completion_tokens": data.get("eval_count", 0)}
        usage["total_tokens"] = usage["prompt_tokens"] + usage["completion_tokens"]
        return json.loads(data["message"]["content"]), usage
