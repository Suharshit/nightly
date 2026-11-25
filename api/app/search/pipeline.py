"""The whole search for one request: profile -> filter -> retrieve -> fuse -> rerank ->
personalise -> diversify -> reasons. /matches uses it now; the agent's search_jobs tool later.
"""

from dataclasses import dataclass, field

from api.app import profile as prof
from api.app.search.hybrid import FUSED, Filters, infer_level, search
from api.app.search.personalise import personalise
from api.app.search.rerank import rerank


class NeedsQuery(ValueError):
    """No query and no resume to stand in for one."""


@dataclass
class Request:
    q: str = ""
    level: str | None = None
    cities: list[str] = field(default_factory=list)
    remote: bool = False
    limit: int = 20
    use_keyword: bool = True
    use_vector: bool = True
    use_rerank: bool = True
    use_profile: bool = True
    log_shown: bool = True


@dataclass
class Result:
    jobs: list[dict]
    level: str | None
    mode: str          # "query" or "feed" (no query: the resume stands in)


def to_pgvector(vec: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"


def run(pool, embedder, reranker, req: Request, user: dict | None) -> Result:
    p = None
    if user:
        with pool.connection() as conn, conn.cursor() as cur:
            p = prof.load_profile(cur, user["id"])
    prefs = p.prefs if p else {}
    q = req.q.strip()
    # Explicit request filters win; otherwise the saved preferences apply.
    level = req.level or (infer_level(q) if q else None) or prefs.get("level")
    cities = req.cities or prefs.get("cities") or []
    remote = req.remote or bool(prefs.get("remote"))

    if q:
        mode, keyword_text, rerank_text = "query", q, q
        qvec = to_pgvector(embedder.query(q)) if req.use_vector else None
    else:
        if p is None or p.resume_vec is None:
            raise NeedsQuery("Type what you're looking for, or upload your resume first.")
        mode, rerank_text = "feed", prof.summary(p)
        keyword_text = " ".join(f'"{s}"' if " " in s else s for s in p.resume_skills[:6])
        qvec = p.resume_vec if req.use_vector else None

    f = Filters(level=level, cities=cities, remote=remote,
                exclude_ids=p.exclude_ids if p else [])
    with pool.connection() as conn, conn.cursor() as cur:
        jobs = search(cur, keyword_text, qvec, f, use_keyword=req.use_keyword,
                      use_vector=req.use_vector, limit=FUSED,
                      taste=p.taste if p and req.use_profile else None)
    if req.use_rerank:
        jobs = rerank(reranker, rerank_text, jobs)
    jobs = personalise(jobs, p, use_profile=req.use_profile)[:req.limit]
    if p and req.log_shown and jobs:
        with pool.connection() as conn, conn.cursor() as cur:
            prof.log_shown(cur, p.user_id, [j["id"] for j in jobs])
    return Result(jobs=jobs, level=level, mode=mode)
