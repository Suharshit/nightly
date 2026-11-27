"""FastAPI routes. Run locally: uvicorn api.app.main:app --port 8000"""

import os
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from api.app import profile as prof
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


app = FastAPI(title="nightly", lifespan=lifespan)

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
    jobs: list[Job]


@app.get("/health")
def health(request: Request) -> dict:
    with request.app.state.pool.connection() as conn:
        conn.execute("select 1")
    return {"ok": True}


@app.get("/matches", response_model=Matches)
def matches(
    request: Request,
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
) -> Matches:
    """With q: search. Without q (signed in, resume uploaded): the personal feed."""
    started = time.perf_counter()
    req = pipeline.Request(q=q, level=level, cities=city or [], remote=remote, limit=limit,
                           use_keyword=keyword, use_vector=vector, use_rerank=rerank,
                           use_profile=personalise)
    st = request.app.state
    try:
        res = pipeline.run(st.pool, st.embedder, st.reranker, req, user)
    except pipeline.NeedsQuery as e:
        raise HTTPException(400, str(e)) from e
    took = int((time.perf_counter() - started) * 1000)
    return Matches(q=q, mode=res.mode, level=res.level,
                   personalised=bool(user) and personalise, count=len(res.jobs),
                   took_ms=took, jobs=[Job(**j) for j in res.jobs])


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


@app.patch("/prefs")
def set_prefs(request: Request, body: Prefs,
              user: Annotated[dict, Depends(current_user)]) -> dict:
    """Onboarding chips: role type, location, experience. Only the fields sent change."""
    patch = body.model_dump(exclude_unset=True)
    with request.app.state.pool.connection() as conn, conn.cursor() as cur:
        try:
            return {"prefs": prof.update_prefs(cur, user, patch)}
        except ValueError as e:
            raise HTTPException(422, str(e)) from e


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
    return ResumeOut(chars=len(text), skills=skills)


class Me(BaseModel):
    email: str | None
    has_resume: bool
    resume_skills: list[str]
    prefs: dict


@app.get("/me", response_model=Me)
def me(request: Request, user: Annotated[dict, Depends(current_user)]) -> Me:
    with request.app.state.pool.connection() as conn, conn.cursor() as cur:
        cur.execute("select resume_text is not null, coalesce(resume_skills, '{}'), "
                    "coalesce(prefs, '{}') from profiles where user_id = %s", (user["id"],))
        row = cur.fetchone()
    if row is None:
        return Me(email=user["email"], has_resume=False, resume_skills=[], prefs={})
    return Me(email=user["email"], has_resume=row[0], resume_skills=row[1], prefs=row[2])


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=500)


class ChatOut(BaseModel):
    reply: str
    jobs: list[dict]          # cards in the order the agent ranked them, each with its reason
    follow_up_chips: list[str]
    json_valid: bool
    took_ms: int


@app.post("/chat", response_model=ChatOut)
def chat(request: Request, body: ChatIn,
         user: Annotated[dict | None, Depends(optional_user)]) -> ChatOut:
    """Signed in: memory and saved preferences. Anonymous: a one-off search chat."""
    st = request.app.state
    if st.llm is None:
        raise HTTPException(503, "Chat is not configured on this server.")
    started = time.perf_counter()
    turn = Agent(st.pool, st.embedder, st.reranker, st.llm).respond(user, body.message.strip())
    jobs = [c | {"reason": turn.reply.reasons.get(c["id"]) or c["reason"]} for c in turn.jobs]
    return ChatOut(reply=turn.reply.reply, jobs=jobs, follow_up_chips=turn.reply.follow_up_chips,
                   json_valid=turn.json_valid,
                   took_ms=int((time.perf_counter() - started) * 1000))
