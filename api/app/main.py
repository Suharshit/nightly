"""FastAPI routes. Run locally: uvicorn api.app.main:app --port 8000"""

import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel

from api.app.auth import current_user
from api.app.resume import MAX_BYTES, ResumeError, embed_text, pdf_text, resume_skills
from api.app.search.hybrid import Filters, infer_level, search


def to_pgvector(vec: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Tests set these first, with a fake embedder and their own pool.
    if not hasattr(app.state, "pool"):
        from api.app.db import make_pool
        app.state.pool = make_pool()
    if not hasattr(app.state, "embedder"):
        from api.app.models import Embedder
        app.state.embedder = Embedder()
    if not hasattr(app.state, "auth"):
        from api.app.auth import SupabaseAuth
        app.state.auth = SupabaseAuth()
    yield
    app.state.pool.close()


app = FastAPI(title="nightly", lifespan=lifespan)


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
    score: float
    keyword_rank: int | None
    vector_rank: int | None


class Matches(BaseModel):
    q: str
    level: str | None
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
    q: Annotated[str, Query(min_length=1, max_length=200)],
    level: Literal["student", "fresher", "junior"] | None = None,
    city: Annotated[list[str] | None, Query()] = None,
    remote: bool = False,
    limit: Annotated[int, Query(ge=1, le=30)] = 20,
    keyword: bool = True,
    vector: bool = True,
) -> Matches:
    started = time.perf_counter()
    level = level or infer_level(q)
    qvec = to_pgvector(request.app.state.embedder.query(q)) if vector else None
    f = Filters(level=level, cities=city or [], remote=remote)
    with request.app.state.pool.connection() as conn, conn.cursor() as cur:
        jobs = search(cur, q, qvec, f, use_keyword=keyword, use_vector=vector, limit=limit)
    took = int((time.perf_counter() - started) * 1000)
    return Matches(q=q, level=level, count=len(jobs), took_ms=took,
                   jobs=[Job(**j) for j in jobs])


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
