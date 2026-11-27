"""Groq chat completions with tools (OpenAI-compatible).

Limits are per model and per organisation (free tier: 30 RPM, 8K TPM), so the budget comes
from Groq's x-ratelimit-* headers, not from guesses. A chat user should not wait a minute
for the token window to reset, so when the main model is short of tokens, or still returns
429 after one quick retry, the call goes to the fallback model instead. The caller logs
which model answered.
"""

import os
import time

import httpx

from worker.llm import GROQ_URL, _seconds

MAX_WAIT = 20.0   # seconds a chat turn may wait when both models are out of tokens


class LLMError(RuntimeError):
    pass


class ToolUseFailed(LLMError):
    """The model produced a malformed tool call (a tool that does not exist, an argument the
    schema does not allow, or a tool call when none was on offer). Groq returns what the
    model generated as `failed_generation`, which the loop can often still use."""

    def __init__(self, message: str, failed_generation: str = ""):
        super().__init__(message)
        self.failed_generation = failed_generation or ""


class GroqChat:
    def __init__(self, model: str | None = None, fallback: str | None = None,
                 timeout: float = 30):
        self.model = model or os.getenv("AGENT_MODEL", "openai/gpt-oss-120b")
        self.fallback = fallback or os.getenv("FALLBACK_MODEL", "openai/gpt-oss-20b")
        self.key = os.environ["GROQ_API_KEY"]
        self.client = httpx.Client(timeout=timeout)
        self.budget: dict[str, tuple[int, float]] = {}  # model -> (tokens left, reset time)

    def _short(self, model: str, need: int) -> float:
        """0 if the model can take `need` tokens now, else seconds until its window resets."""
        left, reset = self.budget.get(model, (None, 0.0))
        wait = reset - time.monotonic()
        return wait if left is not None and left < need and wait > 0 else 0.0

    def _note(self, model: str, headers) -> None:
        left = headers.get("x-ratelimit-remaining-tokens")
        if left is not None and left.isdigit():
            self.budget[model] = (int(left), time.monotonic() +
                                  _seconds(headers.get("x-ratelimit-reset-tokens")))

    def chat(self, messages: list[dict], tools: list[dict] | None = None,
             json_only: bool = False, max_tokens: int = 700) -> tuple[dict, dict, str]:
        """Returns (assistant message, usage, model used)."""
        need = sum(len(str(m.get("content") or "")) for m in messages) // 4 + max_tokens
        need += 700 if tools else 0
        models = [m for m in (self.model, self.fallback) if not self._short(m, need)]
        if not models:   # both short: wait for the sooner reset, then use that model
            waits = {m: self._short(m, need) for m in (self.model, self.fallback)}
            model = min(waits, key=waits.get)
            time.sleep(min(waits[model], MAX_WAIT))
            models = [model]
        for model in models:
            body: dict = {"model": model, "messages": messages, "temperature": 0.2,
                          "max_completion_tokens": max_tokens}
            if model.startswith("openai/gpt-oss"):
                body["reasoning_effort"] = "low"
            if tools:
                body["tools"], body["tool_choice"] = tools, "auto"
            if json_only:
                body["response_format"] = {"type": "json_object"}
            for attempt in range(2):
                r = self.client.post(GROQ_URL, json=body,
                                     headers={"Authorization": f"Bearer {self.key}"})
                self._note(model, r.headers)
                if r.status_code == 429:
                    wait = _seconds(r.headers.get("retry-after"))
                    if attempt == 0 and wait <= 3:
                        time.sleep(max(wait, 1.0))
                        continue
                    break                                   # try the next model
                if r.status_code == 400 and "tool_use_failed" in r.text:
                    try:
                        failed = (r.json().get("error") or {}).get("failed_generation") or ""
                    except ValueError:
                        failed = ""
                    raise ToolUseFailed(f"{model}: {r.text[:300]}", failed)
                if r.status_code >= 400:
                    raise LLMError(f"{model}: HTTP {r.status_code}: {r.text[:300]}")
                data = r.json()
                return data["choices"][0]["message"], data.get("usage") or {}, model
        raise LLMError("rate limited on both models")
