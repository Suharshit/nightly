"""FastAPI routes. Run locally: uvicorn api.app.main:app --port 8000"""

import math
import os
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from api.app import admin as adm
from api.app import limits
from api.app import profile as prof
from api.app.admin import admin_user, is_admin
from api.app.agent.loop import Agent
from api.app.auth import current_user, optional_user
from api.app.resume import MAX_BYTES, ResumeError, embed_text, pdf_text, resume_skills
from api.app.search import pipeline
from api.app.search.pipeline import to_pgvector


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Tests set these first, with fake models and their own pool.
    if not hasattr(app.state, "pool"):
        from api.app.db import make_pool
        app.state.pool = make_pool()
    if not hasattr(app.state, "embedder"):
        from api.app.models import Embedder
        app.state.embedder = Embedder()
    if not hasattr(app.state, "reranker"):
        from api.app.models import Reranker
        app.state.reranker = Reranker()
    if not hasattr(app.state, "llm"):
        try:
            from api.app.agent.llm import GroqChat
            app.state.llm = GroqChat()
        except KeyError:      # no GROQ_API_KEY: everything but /chat still works
            app.state.llm = None
    if not hasattr(app.state, "auth"):
        from api.app.auth import SupabaseAuth
        app.state.auth = SupabaseAuth()
    yield
    app.state.pool.close()


# No /docs, /redoc or /openapi.json: they would list every route, admin ones included, to anyone.
app = FastAPI(title="nightly", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

# Upload size and rate limits. Added before CORS, so CORS wraps it and its 413/429 answers
# still carry CORS headers (the browser can then read the message).
app.middleware("http")(limits.guard)

# The web app calls the API from the browser. APP_BASE_URL may list several origins,
# comma-separated (e.g. the Vercel URL and a preview URL).
_origins = {o.strip().rstrip("/") for o in os.getenv("APP_BASE_URL", "").split(",") if o.strip()}
app.add_middleware(CORSMiddleware, allow_origins=sorted(_origins | {"http://localhost:3000"}),
                   allow_methods=["GET", "POST", "PATCH", "DELETE"],
                   allow_headers=["Authorization", "Content-Type"])


class Job(BaseModel):
    id: int
    title: str
    company: str
    city: str | None
    work_mode: str | None
    remote: bool | None
    seniority: str | None
    min_exp_years: int | None
    max_exp_years: int | None
    skills: list[str]
    apply_url: str | None
    posted_at: datetime | None
    reason: str
    final_score: float
    score: float                       # fused (RRF)
    keyword_rank: int | None
    vector_rank: int | None
    rerank_score: float | None = None
    parts: dict[str, float]            # taste, skills, fresh, penalty: for debugging and evals


class Matches(BaseModel):
    q: str
    mode: str
    level: str | None
    personalised: bool
    count: int
    took_ms: int
    timings: dict[str, float] = {}     # ms per pipeline stage (also in the Server-Timing header)
    jobs: list[Job]


@app.get("/health")
def health(request: Request) -> dict:
    """Up, and one database round trip from this server (db_ms), to tell network from work."""
    with request.app.state.pool.connection() as conn:
        t = time.perf_counter()
        conn.execute("select 1")
        db_ms = round((time.perf_counter() - t) * 1000, 1)
    return {"ok": True, "db_ms": db_ms}


def log_shown_later(pool, user_id: str, job_ids: list[int]) -> None:
    with pool.connection() as conn, conn.cursor() as cur:
        prof.log_shown(cur, user_id, job_ids)


@app.get("/matches", response_model=Matches)
def matches(
    request: Request,
    response: Response,
    background: BackgroundTasks,
    user: Annotated[dict | None, Depends(optional_user)],
    q: Annotated[str, Query(max_length=200)] = "",
    level: Literal["student", "fresher", "junior"] | None = None,
    city: Annotated[list[str] | None, Query()] = None,
    remote: bool = False,
    limit: Annotated[int, Query(ge=1, le=30)] = 20,
    keyword: bool = True,
    vector: bool = True,
    rerank: bool = True,
    personalise: bool = True,
    new: bool = False,
) -> Matches:
    """With q: search. Without q (signed in, resume uploaded): the personal feed.
    new=true keeps only jobs the latest nightly run added ("New since yesterday")."""
    started = time.perf_counter()
    req = pipeline.Request(q=q, level=level, cities=city or [], remote=remote, limit=limit,
                           use_keyword=keyword, use_vector=vector, use_rerank=rerank,
                           use_profile=personalise, new_only=new,
                           log_shown=False, defer_shown=True)
    st = request.app.state
    try:
        res = pipeline.run(st.pool, st.embedder, st.reranker, req, user)
    except pipeline.NeedsQuery as e:
        raise HTTPException(400, str(e)) from e
    if res.shown_by:   # after the response: the user does not wait for this write
        background.add_task(log_shown_later, st.pool, res.shown_by, [j["id"] for j in res.jobs])
    took = int((time.perf_counter() - started) * 1000)
    response.headers["Server-Timing"] = ", ".join(
        [f"{name};dur={ms}" for name, ms in res.timings.items()] + [f"total;dur={took}"])
    return Matches(q=q, mode=res.mode, level=res.level,
                   personalised=bool(user) and personalise, count=len(res.jobs),
                   took_ms=took, timings=res.timings, jobs=[Job(**j) for j in res.jobs])


class Feedback(BaseModel):
    job_id: int
    action: Literal["like", "dislike", "apply_click", "share"]
    reason: Literal["too_senior", "wrong_location", "not_interested"] | None = None


@app.post("/feedback")
def feedback(request: Request, body: Feedback,
             user: Annotated[dict, Depends(current_user)]) -> dict:
    # One transaction: the interaction and the taste/avoid update land together or not at all.
    with request.app.state.pool.connection() as conn, conn.transaction():
        try:
            with conn.cursor() as cur:
                changed = prof.record_feedback(cur, user, body.job_id, body.action,
                                               body.reason)
        except LookupError as e:
            raise HTTPException(404, "That job no longer exists.") from e
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
    return {"ok": True, "changed": changed}


class Prefs(BaseModel):
    roles: list[str] | None = None
    cities: list[str] | None = None
    remote: bool | None = None
    level: Literal["student", "fresher", "junior"] | None = None
    # Where the user came from (?ref=wa_share, wa_group, linkedin) for signup stats.
    ref: str | None = Field(default=None, pattern=r"^[a-z0-9_-]{1,32}$")


# The first source wins: later visits from other links do not overwrite it.
SET_REF = ("update profiles set prefs = coalesce(prefs, '{}') || jsonb_build_object('ref', %s) "
           "where user_id = %s and not coalesce(prefs, '{}') ? 'ref' returning prefs")


@app.patch("/prefs")
def set_prefs(request: Request, body: Prefs,
              user: Annotated[dict, Depends(current_user)]) -> dict:
    """Onboarding chips: role type, location, experience. Only the fields sent change."""
    patch = body.model_dump(exclude_unset=True)
    ref = patch.pop("ref", None)
    with request.app.state.pool.connection() as conn, conn.cursor() as cur:
        try:
            prefs = prof.update_prefs(cur, user, patch)
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        if ref:
            cur.execute(SET_REF, (ref, user["id"]))
            row = cur.fetchone()
            prefs = row[0] if row else prefs
    return {"prefs": prefs}


@app.get("/stats")
def stats(request: Request, user: Annotated[dict, Depends(admin_user)]) -> dict:
    """Usage numbers for the README: users, chat, feedback, jobs. Admins only."""
    with request.app.state.pool.connection() as conn, conn.cursor() as cur:
        return adm.stats(cur)


SAVE_RESUME = """
insert into profiles (user_id, email, resume_text, resume_embedding, resume_skills)
values (%(user_id)s, %(email)s, %(text)s, %(vec)s::vector, %(skills)s)
on conflict (user_id) do update set email = excluded.email,
  resume_text = excluded.resume_text, resume_embedding = excluded.resume_embedding,
  resume_skills = excluded.resume_skills
"""


class ResumeOut(BaseModel):
    chars: int
    skills: list[str]


@app.post("/resume", response_model=ResumeOut)
def upload_resume(request: Request, file: UploadFile,
                  user: Annotated[dict, Depends(current_user)]) -> ResumeOut:
    data = file.file.read(MAX_BYTES + 1)
    try:
        text = pdf_text(data)
    except ResumeError as e:
        raise HTTPException(422, str(e)) from e
    skills = resume_skills(text)
    vec = to_pgvector(request.app.state.embedder.query(embed_text(skills, text)))
    with request.app.state.pool.connection() as conn:
        conn.execute(SAVE_RESUME, {"user_id": user["id"], "email": user["email"], "text": text,
                                   "vec": vec, "skills": skills})
    prof.forget_profile(user["id"])
    return ResumeOut(chars=len(text), skills=skills)


class Me(BaseModel):
    email: str | None
    has_resume: bool
    resume_skills: list[str]
    prefs: dict
    links: list[dict] | None = None   # admins only; /me leaves the key out for everyone else


@app.get("/me", response_model=Me)
def me(request: Request, user: Annotated[dict, Depends(current_user)]) -> JSONResponse:
    with request.app.state.pool.connection() as conn, conn.cursor() as cur:
        cur.execute("select resume_text is not null, coalesce(resume_skills, '{}'), "
                    "coalesce(prefs, '{}') from profiles where user_id = %s", (user["id"],))
        row = cur.fetchone()
    has, skills, prefs = row if row is not None else (False, [], {})
    body = Me(email=user["email"], has_resume=has, resume_skills=skills, prefs=prefs).model_dump()
    if is_admin(user):
        body["links"] = adm.ADMIN_LINKS
    else:
        del body["links"]
    return JSONResponse(body)


# Deleting the Supabase login removes everything else: auth identities and sessions, and our
# profiles row, which cascades to interactions, messages and digests_sent. agent_logs has no
# foreign key (it keeps metrics), so its rows for this user go explicitly.
DELETE_USER = [
    "delete from agent_logs where user_id = %(id)s",
    # Bug reports stay for the owner, but lose the email and the link to the account.
    "update bug_reports set email = null, user_id = null where user_id = %(id)s",
    "delete from auth.users where id = %(id)s",
]


@app.delete("/me")
def delete_me(request: Request, user: Annotated[dict, Depends(current_user)]) -> dict:
    """Delete my data: the account, resume, preferences, activity and chat history."""
    with request.app.state.pool.connection() as conn, conn.cursor() as cur:
        with conn.transaction():
            for sql in DELETE_USER:
                cur.execute(sql, {"id": user["id"]})
    forget = getattr(request.app.state.auth, "forget", None)
    if forget:
        forget(user["id"])
    prof.forget_profile(user["id"])
    return {"deleted": True}


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=500)


class ChatOut(BaseModel):
    reply: str
    jobs: list[dict]          # cards in the order the agent ranked them, each with its reason
    follow_up_chips: list[str]
    json_valid: bool
    took_ms: int
    chats_left: int           # messages left in this user's rolling 24-hour allowance


# Groq's free tier gives each model 200K tokens a day for everyone together, and one chat turn
# takes ~6-8K tokens over 2-3 calls, so a few heavy users could empty it. Each user gets this
# many messages per rolling 24 hours; matches and search are not limited.
CHAT_DAILY_LIMIT = int(os.getenv("CHAT_DAILY_LIMIT", "10"))
CHAT_QUOTA = ("select count(*), min(created_at) from messages where user_id = %s "
              "and role = 'user' and created_at > now() - interval '24 hours'")


def chat_quota(pool, user_id: str) -> tuple[int, datetime | None]:
    """Messages this user sent in the last 24 hours, and when the oldest of them was sent."""
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute(CHAT_QUOTA, (user_id,))
        row = cur.fetchone()
    return (row[0], row[1]) if row else (0, None)


@app.post("/chat", response_model=ChatOut)
def chat(request: Request, body: ChatIn,
         user: Annotated[dict, Depends(current_user)]) -> ChatOut:
    """One chat turn, with memory and saved preferences. Signed-in users only, capped per day."""
    st = request.app.state
    if st.llm is None:
        raise HTTPException(503, "Chat is not configured on this server.")
    admin = is_admin(user)                 # the owner tests without the cap
    used, oldest = (0, None) if admin else chat_quota(st.pool, user["id"])
    if used >= CHAT_DAILY_LIMIT:
        wait = "tomorrow"
        if oldest is not None:
            hours = (oldest + timedelta(hours=24) - datetime.now(UTC)).total_seconds() / 3600
            wait = f"in about {max(1, math.ceil(hours))} h"
        raise HTTPException(429, f"You've used today's {CHAT_DAILY_LIMIT} chat messages. "
                                 f"Your matches still work, and chat opens again {wait}.")
    started = time.perf_counter()
    turn = Agent(st.pool, st.embedder, st.reranker, st.llm).respond(user, body.message.strip())
    jobs = [c | {"reason": turn.reply.reasons.get(c["id"]) or c["reason"]} for c in turn.jobs]
    return ChatOut(reply=turn.reply.reply, jobs=jobs, follow_up_chips=turn.reply.follow_up_chips,
                   json_valid=turn.json_valid,
                   took_ms=int((time.perf_counter() - started) * 1000),
                   chats_left=max(0, CHAT_DAILY_LIMIT - used - 1))


class BugIn(BaseModel):
    message: str = Field(min_length=5, max_length=2000)
    page: str | None = Field(default=None, max_length=200)
    email: str | None = Field(default=None, max_length=200,
                              pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


SAVE_BUG = """insert into bug_reports (user_id, email, page, message, user_agent)
values (%s, %s, %s, %s, %s) returning id"""


@app.post("/bugs")
def report_bug(request: Request, body: BugIn,
               user: Annotated[dict | None, Depends(optional_user)]) -> dict:
    """A bug report from the app's /bug page. Signing in is optional; the owner reads these
    on /stats. Rate-limited per visitor (limits.RATES)."""
    agent = (request.headers.get("user-agent") or "")[:300] or None
    with request.app.state.pool.connection() as conn, conn.cursor() as cur:
        cur.execute(SAVE_BUG, (user["id"] if user else None, body.email or None,
                               body.page, body.message.strip(), agent))
        (bug_id,) = cur.fetchone()
    return {"id": bug_id}
