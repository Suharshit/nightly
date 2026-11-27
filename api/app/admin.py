"""Admins (the owner) and the /stats numbers the README quotes.

ADMIN_EMAILS is a comma-separated list. Admin accounts skip the chat cap and are left out of
every user metric, so the owner's own testing does not inflate the numbers. Deleted accounts
are gone from the tables, so they are not counted either.
"""

import os
from typing import Annotated

from fastapi import Depends, HTTPException

from api.app.auth import current_user


def admin_emails() -> list[str]:
    return [e.strip().lower() for e in os.getenv("ADMIN_EMAILS", "").split(",") if e.strip()]


def is_admin(user: dict | None) -> bool:
    return bool(user and (user.get("email") or "").lower() in admin_emails())


def admin_user(user: Annotated[dict, Depends(current_user)]) -> dict:
    if not is_admin(user):
        raise HTTPException(403, "Admins only.")
    return user


# Real users: every account except the admins'.
USERS = "select id from auth.users where lower(coalesce(email, '')) <> all(%(admins)s::text[])"

STATS_SQL = {
    "users": f"""
        select count(*),
               count(*) filter (where u.created_at > now() - interval '24 hours'),
               count(*) filter (where u.created_at > now() - interval '7 days'),
               count(p.resume_text)
        from auth.users u left join profiles p on p.user_id = u.id
        where u.id in ({USERS})""",
    "sources": f"""
        select coalesce(nullif(p.prefs->>'ref', ''), 'direct') as source, count(*)
        from auth.users u left join profiles p on p.user_id = u.id
        where u.id in ({USERS}) group by 1 order by 2 desc, 1""",
    "active": f"""
        select count(distinct user_id) from (
          select user_id from interactions where created_at > now() - interval '7 days'
          union all
          select user_id from messages where role = 'user'
            and created_at > now() - interval '7 days') a
        where user_id in ({USERS})""",
    "chat": f"""
        select count(distinct user_id), count(*) from messages
        where role = 'user' and user_id in ({USERS})""",
    "turns": f"""
        select count(*),
               avg(json_valid::int),
               percentile_cont(0.5) within group (order by latency_ms),
               percentile_cont(0.95) within group (order by latency_ms),
               avg((model <> %(agent_model)s)::int)
        from agent_logs where user_id in ({USERS})""",
    "feedback": f"""
        select count(*) filter (where action = 'shown'),
               count(*) filter (where action = 'like'),
               count(*) filter (where action = 'dislike'),
               count(*) filter (where action = 'apply_click'),
               count(*) filter (where action = 'share')
        from interactions where user_id in ({USERS})""",
    "jobs": """
        select count(*) filter (where j.is_active),
               count(distinct j.company_id) filter (where j.is_active)
        from jobs j""",
    "bugs": """
        select id, created_at, page, message, email, status from bug_reports
        order by created_at desc limit 50""",
    "bug_counts": """
        select count(*), count(*) filter (where status = 'open') from bug_reports""",
    "ingest": """
        select started_at, inserted, expired from ingest_runs
        order by started_at desc limit 1""",
}


def _ratio(a, b) -> float | None:
    return round(a / b, 4) if b else None


def _num(x) -> float | None:
    return None if x is None else round(float(x), 4)


def stats(cur) -> dict:
    """Every number on /stats, straight from the tables."""
    p = {"admins": admin_emails(), "agent_model": os.getenv("AGENT_MODEL", "openai/gpt-oss-120b")}

    def one(key):
        cur.execute(STATS_SQL[key], p)
        return cur.fetchone()

    signups, day, week, resumes = one("users")
    cur.execute(STATS_SQL["sources"], p)
    sources = {src: n for src, n in cur.fetchall()}
    (active,) = one("active")
    chat_users, user_messages = one("chat")
    turns, valid, p50, p95, fallback = one("turns")
    shown, likes, dislikes, applies, shares = one("feedback")
    active_jobs, companies = one("jobs")
    ingest = one("ingest")
    bugs_total, bugs_open = one("bug_counts")
    cur.execute(STATS_SQL["bugs"], p)
    bugs = [{"id": i, "created_at": t.isoformat(), "page": pg, "message": m, "email": e,
             "status": st} for i, t, pg, m, e, st in cur.fetchall()]
    return {
        "users": {"signups": signups, "signups_24h": day, "signups_7d": week,
                  "with_resume": resumes, "active_7d": active, "by_source": sources},
        "chat": {"users": chat_users, "messages": user_messages,
                 "messages_per_chat_user": _ratio(user_messages, chat_users),
                 "agent_turns": turns, "json_valid_rate": _num(valid),
                 "latency_ms_p50": _num(p50), "latency_ms_p95": _num(p95),
                 "fallback_rate": _num(fallback)},
        "feedback": {"shown": shown, "likes": likes, "dislikes": dislikes,
                     "apply_clicks": applies, "shares": shares,
                     "like_rate": _ratio(likes, shown), "apply_rate": _ratio(applies, shown)},
        "jobs": {"active": active_jobs, "companies": companies,
                 "last_ingest": None if ingest is None else {
                     "started_at": ingest[0].isoformat(), "inserted": ingest[1],
                     "expired": ingest[2]}},
        "bugs": {"total": bugs_total, "open": bugs_open, "latest": bugs},
        "excludes": "admin accounts and deleted accounts",
    }
