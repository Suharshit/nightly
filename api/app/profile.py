"""A user's long-term memory: profile, preferences and feedback.

Used by the routes now and by the agent's update_prefs / record_feedback tools later.
"""

import math

from api.app.search.personalise import Profile

LEVELS = ("student", "fresher", "junior")
DISLIKE_REASONS = ("too_senior", "wrong_location", "not_interested")
ACTIONS = ("shown", "like", "dislike", "apply_click", "share")
TASTE_STEP = 0.2       # a like moves the taste vector 20% toward the job
RECENT_DISLIKES = 20
SHOWN_LIMIT = 3        # hide a job after it has been shown this many times

# One round trip: the profile plus everything the hard filter and penalty need.
LOAD = f"""
select p.taste_embedding::text, p.resume_embedding::text, coalesce(p.resume_skills, '{{}}'),
       coalesce(p.prefs, '{{}}'),
       array(select distinct j.company_id
             from (select job_id from interactions
                   where user_id = p.user_id and action = 'dislike'
                   order by created_at desc limit {RECENT_DISLIKES}) d
             join jobs j on j.id = d.job_id),
       array(select job_id from interactions
             where user_id = p.user_id and job_id is not null
             group by job_id
             having bool_or(action = 'dislike')
                 or count(*) filter (where action = 'shown') >= {SHOWN_LIMIT})
from profiles p where p.user_id = %s
"""


def load_profile(cur, user_id: str) -> Profile | None:
    cur.execute(LOAD, (user_id,))
    row = cur.fetchone()
    if row is None:
        return None
    taste, resume_vec, skills, prefs, disliked, exclude = row
    return Profile(user_id=user_id, taste=taste, resume_vec=resume_vec, resume_skills=skills,
                   prefs=prefs, disliked_companies=set(disliked), exclude_ids=list(exclude))


def ensure_profile(cur, user: dict) -> None:
    cur.execute("insert into profiles (user_id, email) values (%s, %s) "
                "on conflict (user_id) do nothing", (user["id"], user.get("email")))


def clean_prefs(patch: dict) -> dict:
    """Only the fields onboarding and the agent may set, with types checked."""
    out: dict = {}
    for key in ("roles", "cities"):
        if key in patch:
            vals = patch[key] or []
            if not isinstance(vals, list) or not all(isinstance(v, str) for v in vals):
                raise ValueError(f"{key} must be a list of strings")
            out[key] = list(dict.fromkeys(v.strip() for v in vals if v.strip()))[:10]
    if "remote" in patch:
        if not isinstance(patch["remote"], bool):
            raise ValueError("remote must be true or false")
        out["remote"] = patch["remote"]
    if "level" in patch:
        if patch["level"] not in (*LEVELS, None):
            raise ValueError(f"level must be one of {', '.join(LEVELS)}")
        out["level"] = patch["level"]
    return out


def update_prefs(cur, user: dict, patch: dict) -> dict:
    ensure_profile(cur, user)
    cur.execute("update profiles set prefs = coalesce(prefs, '{}') || %s::jsonb "
                "where user_id = %s returning prefs", (_json(clean_prefs(patch)), user["id"]))
    return cur.fetchone()[0]


def _json(d: dict) -> str:
    import json
    return json.dumps(d)


def _parse(vec: str) -> list[float]:
    return [float(x) for x in vec.strip("[]").split(",")]


def _unit(v: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def moved_taste(taste: str | None, job_vec: str) -> str:
    """Normalised moving average: taste <- unit(0.8 * taste + 0.2 * job)."""
    job = _parse(job_vec)
    new = job if taste is None else [
        (1 - TASTE_STEP) * t + TASTE_STEP * j for t, j in zip(_parse(taste), job, strict=True)]
    return "[" + ",".join(f"{x:.6f}" for x in _unit(new)) + "]"


def record_feedback(cur, user: dict, job_id: int, action: str,
                    reason: str | None = None) -> dict:
    """Store the interaction; a like moves the taste vector, a dislike reason becomes an
    avoid rule. Returns what changed (for the agent to report back)."""
    if action not in ACTIONS:
        raise ValueError(f"action must be one of {', '.join(ACTIONS)}")
    if reason is not None and (action != "dislike" or reason not in DISLIKE_REASONS):
        raise ValueError(f"reason is only for dislikes: {', '.join(DISLIKE_REASONS)}")
    cur.execute("select embedding::text, company_id, seniority, city from jobs where id = %s",
                (job_id,))
    job = cur.fetchone()
    if job is None:
        raise LookupError("no such job")
    job_vec, company_id, seniority, city = job
    ensure_profile(cur, user)
    cur.execute("insert into interactions (user_id, job_id, action, reason) "
                "values (%s, %s, %s, %s)", (user["id"], job_id, action, reason))
    changed: dict = {}
    if action == "like" and job_vec is not None:
        cur.execute("select taste_embedding::text from profiles where user_id = %s",
                    (user["id"],))
        cur.execute("update profiles set taste_embedding = %s::vector where user_id = %s",
                    (moved_taste(cur.fetchone()[0], job_vec), user["id"]))
        changed["taste"] = "moved toward this job"
    if action == "dislike" and reason:
        key, value = {"too_senior": ("seniority", seniority),
                      "wrong_location": ("cities", city),
                      "not_interested": ("companies", company_id)}[reason]
        if value is not None:
            cur.execute("select coalesce(prefs, '{}') from profiles where user_id = %s "
                        "for update", (user["id"],))
            prefs = cur.fetchone()[0]
            avoid = prefs.setdefault("avoid", {})
            if value not in avoid.setdefault(key, []):
                avoid[key].append(value)
            cur.execute("update profiles set prefs = %s::jsonb where user_id = %s",
                        (_json(prefs), user["id"]))
            changed["avoid"] = {key: value}
    return changed


def log_shown(cur, user_id: str, job_ids: list[int]) -> None:
    if job_ids:
        cur.execute("insert into interactions (user_id, job_id, action) "
                    "select %s, unnest(%s::bigint[]), 'shown'", (user_id, job_ids))


def summary(p: Profile) -> str:
    """Short text standing in for the query when there is none (rerank input, agent context)."""
    prefs = p.prefs
    bits = []
    if prefs.get("roles"):
        bits.append(" / ".join(prefs["roles"]))
    if prefs.get("level"):
        bits.append({"student": "internship", "fresher": "fresher entry level",
                     "junior": "junior 1-2 years"}[prefs["level"]])
    if p.resume_skills:
        bits.append("skills: " + ", ".join(p.resume_skills[:8]))
    return " ".join(bits) or "software engineer"
