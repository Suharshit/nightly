"""The agent's five tools: JSON Schemas for the model, and the code that runs them.

Every job a tool returns is recorded in ctx.seen. The guardrail only lets the final reply
mention jobs in ctx.seen, so the agent cannot invent a job. Results are kept small because
the free tier allows 8K tokens a minute.
"""

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime

from api.app import profile as prof
from api.app.search import pipeline
from api.app.search.personalise import Profile, reason

LEVELS = list(prof.LEVELS)
PREF_FIELDS = ("roles", "cities", "remote", "level")


def _fn(name: str, description: str, props: dict, required: list[str]) -> dict:
    return {"type": "function", "function": {
        "name": name, "description": description,
        "parameters": {"type": "object", "properties": props, "required": required,
                       "additionalProperties": False}}}


_JOB_ID = {"type": "integer", "description": "id of a job from an earlier tool result"}

SCHEMAS = [
    _fn("search_jobs", "Search active jobs for this user. Call before recommending any job.",
        {"query": {"type": "string", "description": "what they want, e.g. 'backend python'"},
         "cities": {"type": "array", "items": {"type": "string"}},
         "work_mode": {"type": "string", "enum": ["remote", "any"]},
         "seniority": {"type": "string", "enum": LEVELS,
                       "description": "student = internships, fresher = 0-1 yrs, junior = 1-2"},
         "skills": {"type": "array", "items": {"type": "string"}},
         "limit": {"type": "integer", "minimum": 1, "maximum": 5}}, []),
    _fn("get_job", "Full details of one job, for 'tell me more'.", {"job_id": _JOB_ID},
        ["job_id"]),
    _fn("update_prefs", "Save a lasting preference, e.g. 'only remote from now on'.",
        {"field": {"type": "string", "enum": list(PREF_FIELDS)},
         "value": {"description": "a string, a list of strings, or true/false for remote"},
         "op": {"type": "string", "enum": ["set", "add", "remove"]}},
        ["field", "value", "op"]),
    _fn("record_feedback", "The user likes or dislikes a job (same as tapping 👍/👎).",
        {"job_id": _JOB_ID, "action": {"type": "string", "enum": ["like", "dislike"]},
         "reason": {"type": "string", "enum": list(prof.DISLIKE_REASONS)}},
        ["job_id", "action"]),
    _fn("explain_match", "Why a job fits or not: matched and missing skills and fit facts.",
        {"job_id": _JOB_ID}, ["job_id"]),
]


@dataclass
class Context:
    pool: object
    embedder: object
    reranker: object
    user: dict | None
    seen: dict[int, dict] = field(default_factory=dict)   # job id -> card, this turn only


def card(j: dict) -> dict:
    """What the UI shows for a job."""
    posted = j.get("posted_at")
    return {"id": j["id"], "title": j["title"], "company": j["company"], "city": j.get("city"),
            "work_mode": j.get("work_mode"), "remote": j.get("remote"),
            "seniority": j.get("seniority"), "min_exp_years": j.get("min_exp_years"),
            "max_exp_years": j.get("max_exp_years"), "skills": j.get("skills") or [],
            "apply_url": j.get("apply_url"),
            "posted_at": posted.isoformat() if isinstance(posted, datetime) else posted,
            "reason": j.get("reason") or ""}


def brief(c: dict) -> dict:
    """What the model sees for a job: a few fields, no URLs."""
    place = "remote" if c.get("work_mode") == "remote" or c.get("remote") else c.get("city")
    lo, hi = c.get("min_exp_years"), c.get("max_exp_years")
    exp = None if lo is None else (f"{lo}-{hi} yrs" if hi is not None else f"{lo}+ yrs")
    return {"id": c["id"], "title": c["title"], "company": c["company"], "place": place,
            "level": c.get("seniority"), "exp": exp, "skills": c["skills"][:5],
            "reason": c["reason"]}


def _need_user(ctx: Context) -> None:
    if not ctx.user:
        raise PermissionError("The user is not signed in, so nothing can be saved. "
                              "Tell them to sign in first.")


def search_jobs(ctx: Context, query: str = "", cities: list[str] | None = None,
                work_mode: str | None = None, seniority: str | None = None,
                skills: list[str] | None = None, limit: int = 5) -> dict:
    q = " ".join([query.strip(), *(skills or [])]).strip()
    req = pipeline.Request(q=q, level=seniority if seniority in LEVELS else None,
                           cities=cities or [], remote=work_mode == "remote",
                           limit=max(1, min(int(limit or 5), 5)), log_shown=False)
    res = pipeline.run(ctx.pool, ctx.embedder, ctx.reranker, req, ctx.user)
    cards = [card(j) for j in res.jobs]
    ctx.seen.update((c["id"], c) for c in cards)
    out: dict = {"count": len(cards), "level_filter": res.level, "jobs": [brief(c) for c in cards]}
    if not cards:
        out["hint"] = "Nothing matched. Suggest loosening one filter."
    return out


JOB = """
select j.id, j.title, c.name, j.city, j.work_mode, j.remote, j.seniority, j.min_exp_years,
       j.max_exp_years, coalesce(j.skills, '{}'), j.apply_url, j.posted_at, j.salary_raw,
       left(j.description_text, 900), j.company_id
from jobs j join companies c on c.id = j.company_id where j.id = %s and j.is_active
"""
_JOB_KEYS = ("id", "title", "company", "city", "work_mode", "remote", "seniority",
             "min_exp_years", "max_exp_years", "skills", "apply_url", "posted_at",
             "salary_raw", "description", "company_id")


def _load_job(ctx: Context, job_id: int) -> tuple[dict, Profile | None]:
    with ctx.pool.connection() as conn, conn.cursor() as cur:
        cur.execute(JOB, (int(job_id),))
        row = cur.fetchone()
        if row is None:
            raise LookupError(f"Job {job_id} is not active any more.")
        p = prof.load_profile(cur, ctx.user["id"]) if ctx.user else None
    job = dict(zip(_JOB_KEYS, row, strict=True))
    job["reason"] = reason(job, p, datetime.now(UTC))
    ctx.seen[job["id"]] = card(job)
    return job, p


def get_job(ctx: Context, job_id: int) -> dict:
    job, _ = _load_job(ctx, job_id)
    return brief(ctx.seen[job["id"]]) | {
        "salary": job["salary_raw"],
        "description": " ".join((job["description"] or "").split())}


def explain_match(ctx: Context, job_id: int) -> dict:
    job, p = _load_job(ctx, job_id)
    mine = {s.lower() for s in (p.resume_skills if p else [])}
    skills = job["skills"]
    prefs = p.prefs if p else {}
    return {"id": job["id"], "title": job["title"], "company": job["company"],
            "matched_skills": [s for s in skills if s.lower() in mine],
            "missing_skills": [s for s in skills if s.lower() not in mine][:8],
            "has_resume": bool(mine),
            "job_level": job["seniority"], "job_exp": brief(ctx.seen[job["id"]])["exp"],
            "wanted_level": prefs.get("level"),
            "job_place": "remote" if job["work_mode"] == "remote" or job["remote"]
            else job["city"],
            "wanted_cities": prefs.get("cities") or [], "wants_remote": prefs.get("remote"),
            "reason": job["reason"]}


def _as_list(value) -> list[str]:
    vals = value if isinstance(value, list) else [value]
    return [str(v).strip() for v in vals if str(v).strip()]


def update_prefs(ctx: Context, field: str, value, op: str = "set") -> dict:
    _need_user(ctx)
    if field not in PREF_FIELDS:
        raise ValueError(f"field must be one of {', '.join(PREF_FIELDS)}")
    with ctx.pool.connection() as conn, conn.cursor() as cur:
        cur.execute("select coalesce(prefs, '{}') from profiles where user_id = %s",
                    (ctx.user["id"],))
        row = cur.fetchone()
        old = (row[0] if row else {}).get(field)
        if field in ("roles", "cities"):
            vals, old = _as_list(value), old or []
            if op == "add":
                new = old + vals
            elif op == "remove":
                drop = {v.lower() for v in vals}
                new = [v for v in old if v.lower() not in drop]
            else:
                new = vals
        elif field == "remote":
            new = False if op == "remove" else value in (True, "true", "yes", 1)
        else:
            new = None if op == "remove" else value
        prefs = prof.update_prefs(cur, ctx.user, {field: new})
    return {"saved": {field: prefs.get(field)}}


def record_feedback(ctx: Context, job_id: int, action: str, reason: str | None = None) -> dict:
    _need_user(ctx)
    if action not in ("like", "dislike"):
        raise ValueError("action must be like or dislike")
    with ctx.pool.connection() as conn, conn.transaction(), conn.cursor() as cur:
        changed = prof.record_feedback(cur, ctx.user, int(job_id), action, reason)
    return {"ok": True, "changed": changed}


RUN = {"search_jobs": search_jobs, "get_job": get_job, "update_prefs": update_prefs,
       "record_feedback": record_feedback, "explain_match": explain_match}


def run(ctx: Context, name: str, arguments: str | dict) -> tuple[dict, bool]:
    """Run one tool call. Errors go back to the model as {"error": ...}, never raised."""
    try:
        args = json.loads(arguments or "{}") if isinstance(arguments, str) else arguments
        if name not in RUN:
            raise ValueError(f"unknown tool {name}")
        return RUN[name](ctx, **args), True
    except pipeline.NeedsQuery as e:
        return {"error": str(e)}, False
    except (LookupError, PermissionError, ValueError, TypeError) as e:
        return {"error": str(e)}, False
