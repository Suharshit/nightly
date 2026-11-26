"""Shared by the agent eval scripts: cases, the owner's expected tools, and the scoring.

convos.jsonl        one chat turn per line: message, saved prefs, earlier messages (proposed)
agent_labels.jsonl  what the owner says the agent should do: {"id", "tools", "args"}
                    tools = [] means "no tool call is right here"; args holds the key
                    arguments per tool, e.g. {"update_prefs": {"field": "remote"}}.
"""

from eval.common import ROOT, load_jsonl

CONVOS = ROOT / "convos.jsonl"
AGENT_LABELS = ROOT / "agent_labels.jsonl"
TOOLS = ["search_jobs", "get_job", "update_prefs", "record_feedback", "explain_match"]

# The arguments worth checking for each tool: (name, how to read what the owner types,
# the only values the agent can send, or None for free values). These choices mirror the
# tool schemas in api/app/agent/tools.py. search_jobs' free-text query is never checked.
KEY_ARGS: dict[str, list[tuple[str, str, list[str] | None]]] = {
    "search_jobs": [("seniority", "str", ["student", "fresher", "junior"]),
                    ("work_mode", "str", ["remote", "any"]), ("cities", "list", None),
                    ("skills", "list", None)],
    "get_job": [("job_id", "int", None)],
    "update_prefs": [("field", "str", ["roles", "cities", "remote", "level"]),
                     ("value", "value", None), ("op", "str", ["set", "add", "remove"])],
    "record_feedback": [("job_id", "int", None), ("action", "str", ["like", "dislike"]),
                        ("reason", "str", ["too_senior", "wrong_location", "not_interested"])],
    "explain_match": [("job_id", "int", None)],
}
HINTS = {
    "seniority": "student = internships, fresher = 0-1 yrs, junior = 1-2 yrs",
    "skills": "only if the turn names a skill that must be passed as a skill",
    "cities": "only cities the user named",
    "value": "text, a comma list, or true/false for remote",
    "job_id": "the number before the job title in the earlier reply",
}


def load_cases() -> list[dict]:
    return load_jsonl(CONVOS)


def load_agent_labels() -> dict[str, dict]:
    """{case id: label}; a later line for the same case overrides an earlier one."""
    return {r["id"]: r for r in load_jsonl(AGENT_LABELS)}


def parse_arg(kind: str, text: str):
    text = text.strip()
    if kind == "int":
        return int(text)
    if kind == "list":
        return [v.strip() for v in text.split(",") if v.strip()]
    if kind == "value":
        if text.lower() in ("true", "false"):
            return text.lower() == "true"
        return [v.strip() for v in text.split(",")] if "," in text else text
    return text


def _norm(v):
    if isinstance(v, str):
        return v.strip().lower()
    if isinstance(v, list):
        return {_norm(x) for x in v}
    return v


def value_matches(expected, actual) -> bool:
    """Strings ignore case; an expected list must be contained in the actual one; a single
    expected string also matches an actual list holding it (update_prefs values)."""
    e, a = _norm(expected), _norm(actual)
    if isinstance(e, set):
        return e <= (a if isinstance(a, set) else {a})
    if isinstance(a, set):
        return e in a
    if isinstance(e, int) and not isinstance(e, bool):
        try:
            return int(actual) == e
        except (TypeError, ValueError):
            return False
    return e == a


def score(label: dict, calls: list[dict]) -> dict:
    """tool_ok: every expected tool was called (or none, when none was expected); extra
    calls are allowed. args_ok: some call of each tool matches all its labelled arguments;
    None when no arguments were labelled."""
    called = [c["name"] for c in calls]
    want = label.get("tools") or []
    tool_ok = not called if not want else set(want) <= set(called)
    args = {t: a for t, a in (label.get("args") or {}).items() if a}
    args_ok = None
    if args:
        args_ok = tool_ok and all(
            any(c["name"] == t and isinstance(c["args"], dict)
                and all(value_matches(v, c["args"].get(k)) for k, v in a.items())
                for c in calls)
            for t, a in args.items())
    return {"tool_ok": tool_ok, "args_ok": args_ok}
