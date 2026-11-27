"""The agent: a plain tool-calling loop. No framework, so every step is visible here.

1. Load context: system prompt, the user's profile summary and the last 10 messages.
2. Call the model with the tools. Run any tool calls, add the results, call again
   (at most 4 tool rounds, then it must answer).
3. The answer must be AgentReply JSON. If it is not, re-ask once with the error; if it still
   is not, fall back to a plain reply and log json_valid = false.
4. Guardrail: drop any job id no tool returned in this turn.
5. Save both messages, log the shown jobs and write one agent_logs row.
"""

import json
import re
import time
from dataclasses import dataclass, field

from pydantic import ValidationError

from api.app import profile as prof
from api.app.agent import prompts, tools
from api.app.agent.llm import LLMError, ToolUseFailed
from api.app.agent.schemas import AgentReply, guard

MAX_ROUNDS = 4
HISTORY = 10
SORRY = "Sorry, I couldn't put an answer together just now. Please try again."


@dataclass
class Turn:
    reply: AgentReply
    jobs: list[dict]                       # cards for reply.job_ids, in order
    json_valid: bool
    model: str
    tool_calls: list[dict] = field(default_factory=list)
    error: str | None = None
    dropped: list[int] = field(default_factory=list)   # invented ids the guardrail removed
    latency_ms: int = 0
    usage: dict = field(default_factory=dict)


def parse(content: str | None) -> tuple[AgentReply | None, str | None]:
    text = re.sub(r"^```(?:json)?|```$", "", (content or "").strip()).strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        return None, "no JSON object found"
    try:
        return AgentReply.model_validate_json(text[start:end + 1]), None
    except ValidationError as e:
        return None, "; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}"
                               for x in e.errors()[:3])


_ALLOWED = {s["function"]["name"]: set(s["function"]["parameters"]["properties"])
            for s in tools.SCHEMAS}


def recover(failed_generation: str, n: int) -> dict | None:
    """Turn a rejected generation back into what the model meant: the final answer (a reply
    sent as a "JSON" tool), or a real tool call minus arguments the schema does not have
    ("location" becomes cities). None if it cannot be read."""
    try:
        data = json.loads(failed_generation or "")
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    args = data.get("arguments", data.get("parameters", data))
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except ValueError:
            return None
    if not isinstance(args, dict):
        return None
    if "reply" in args:
        return {"role": "assistant", "content": json.dumps(args)}
    name = data.get("name")
    if name not in _ALLOWED:
        return None
    clean = {k: v for k, v in args.items() if k in _ALLOWED[name] and v not in ("", None, [])}
    if name == "search_jobs" and isinstance(args.get("location"), str) and \
            args["location"].strip() and "cities" not in clean:
        clean["cities"] = [c.strip() for c in args["location"].split(",") if c.strip()]
    return {"role": "assistant", "content": "", "tool_calls": [
        {"id": f"recovered_{n}", "type": "function",
         "function": {"name": name, "arguments": json.dumps(clean)}}]}


def shown(c: dict) -> str:
    """How a shown job is remembered, so "the Plane one" or "the second one" can be resolved."""
    return f"{c['id']} {c['title']} @ {c['company']}"


def load_history(cur, user_id: str) -> list[dict]:
    cur.execute("select role, content, tool_calls from messages where user_id = %s "
                "order by created_at desc, id desc limit %s", (user_id, HISTORY))
    out = []
    for role, content, extra in reversed(cur.fetchall()):
        extra = (extra or {}) if role == "assistant" else {}
        jobs = extra.get("shown") or [str(i) for i in extra.get("job_ids") or []]
        out.append({"role": role, "content": (content or "") +
                    (f"\n(jobs shown, in order: {'; '.join(jobs)})" if jobs else "")})
    return out


class Agent:
    def __init__(self, pool, embedder, reranker, llm):
        self.pool, self.embedder, self.reranker, self.llm = pool, embedder, reranker, llm

    def respond(self, user: dict | None, message: str) -> Turn:
        started = time.perf_counter()
        ctx = tools.Context(self.pool, self.embedder, self.reranker, user)
        profile, history = None, []
        if user:
            with self.pool.connection() as conn, conn.cursor() as cur:
                profile = prof.load_profile(cur, user["id"])
                history = load_history(cur, user["id"])
        msgs = [{"role": "system", "content": prompts.SYSTEM},
                {"role": "system", "content": prompts.context(profile, bool(user))},
                *history, {"role": "user", "content": message}]
        calls: list[dict] = []
        usage = {"prompt_tokens": 0, "completion_tokens": 0}
        errors: list[str] = []
        model, reply, valid = self.llm.model, None, False

        def ask(**kw) -> dict:
            nonlocal model
            msg, used, model = self.llm.chat(msgs, **kw)
            for k in usage:
                usage[k] += used.get(k) or 0
            return msg

        def ask_safely(with_tools: bool) -> dict:
            """gpt-oss sometimes sends a malformed tool call: its final JSON as a tool named
            "JSON", or a real tool with an argument the schema lacks. Use what it meant
            when Groq returns it; else ask once more, then once with no tools on offer."""
            for kw in ({"tools": tools.SCHEMAS}, {"tools": tools.SCHEMAS}, {}) \
                    if with_tools else ({}, {}):
                try:
                    return ask(**kw)
                except ToolUseFailed as e:
                    fixed = recover(e.failed_generation, len(calls))
                    errors.append("malformed tool call, " + ("recovered" if fixed else "re-asked"))
                    if fixed:
                        return fixed
            raise LLMError("malformed tool calls on every try")

        try:
            for rnd in range(MAX_ROUNDS + 1):
                msg = ask_safely(with_tools=rnd < MAX_ROUNDS)
                if not msg.get("tool_calls"):
                    break
                msgs.append({"role": "assistant", "content": msg.get("content") or "",
                             "tool_calls": msg["tool_calls"]})
                for tc in msg["tool_calls"]:
                    name, args = tc["function"]["name"], tc["function"].get("arguments")
                    result, ok = tools.run(ctx, name, args)
                    calls.append({"name": name, "args": _args(args), "ok": ok})
                    msgs.append({"role": "tool", "tool_call_id": tc["id"],
                                 "content": json.dumps(result, default=str)})
            reply, err = parse(msg.get("content"))
            if reply is None:
                msgs += [{"role": "assistant", "content": msg.get("content") or ""},
                         {"role": "user", "content": prompts.RETRY.format(error=err)}]
                try:
                    msg = ask(json_only=True)
                except LLMError:       # JSON mode itself can fail validation; ask plainly
                    errors.append("JSON mode failed, re-asked plainly")
                    msg = ask_safely(with_tools=False)
                reply, err = parse(msg.get("content"))
            valid = reply is not None
            if reply is None:
                errors.append(f"invalid JSON twice: {err}")
                text = (msg.get("content") or "").strip()
                reply = AgentReply(reply=text[:600] if text and "{" not in text else SORRY)
        except LLMError as e:
            errors.append(str(e)[:300])
            reply = AgentReply(reply=SORRY)

        reply, dropped = guard(reply, ctx.seen)
        if dropped:
            errors.append(f"dropped job ids no tool returned: {dropped}")
        if model != self.llm.model:
            errors.append(f"answered by fallback model {model}")
        turn = Turn(reply=reply, jobs=[ctx.seen[j] for j in reply.job_ids], json_valid=valid,
                    model=model, tool_calls=calls, error="; ".join(errors) or None,
                    dropped=dropped, usage=usage,
                    latency_ms=int((time.perf_counter() - started) * 1000))
        self._save(user, message, turn, usage, turn.latency_ms)
        return turn

    def _save(self, user, message: str, turn: Turn, usage: dict, latency_ms: int) -> None:
        with self.pool.connection() as conn, conn.transaction(), conn.cursor() as cur:
            if user:
                prof.ensure_profile(cur, user)
                cur.execute("insert into messages (user_id, role, content, tool_calls) values "
                            "(%s, 'user', %s, null), (%s, 'assistant', %s, %s::jsonb)",
                            (user["id"], message, user["id"], turn.reply.reply,
                             json.dumps({"calls": turn.tool_calls,
                                         "job_ids": turn.reply.job_ids,
                                         "shown": [shown(c) for c in turn.jobs]})))
                prof.log_shown(cur, user["id"], turn.reply.job_ids)
            cur.execute("insert into agent_logs (user_id, model, latency_ms, prompt_tokens, "
                        "completion_tokens, tool_calls, json_valid, error) "
                        "values (%s, %s, %s, %s, %s, %s::jsonb, %s, %s)",
                        (user["id"] if user else None, turn.model, latency_ms,
                         usage["prompt_tokens"], usage["completion_tokens"],
                         json.dumps(turn.tool_calls), turn.json_valid, turn.error))


def _args(raw) -> dict | str:
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw or "{}")
    except ValueError:
        return raw
