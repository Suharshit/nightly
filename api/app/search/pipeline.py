"""The whole search for one request: profile -> filter -> retrieve -> fuse -> rerank ->
personalise -> diversify -> reasons. /matches uses it now; the agent's search_jobs tool later.
"""

import time
from contextlib import contextmanager
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
    use_final: bool = True   # freshness + profile terms + diversity; off = rerank/fused order
    # None = by mode: on for the query-less feed, off for searches with a query (eval).
    use_fresh: bool | None = None
    use_diversity: bool | None = None
    log_shown: bool = True
    defer_shown: bool = False  # don't log here; Result.shown_by tells the caller whom to log for
    new_only: bool = False   # "New since yesterday": only jobs the latest nightly run added
    hide_unknown_level: bool = False  # True leaves out jobs stating no level or years


@dataclass
class Result:
    jobs: list[dict]
    level: str | None
    mode: str          # "query" or "feed" (no query: the resume stands in)
    timings: dict[str, float] = field(default_factory=dict)  # ms per stage, in order
    shown_by: str | None = None    # user to log these jobs as "shown" for, when not logged here


class Stages:
    """Wall-clock milliseconds per pipeline stage, to see where a request spends its time."""

    def __init__(self):
        self.ms: dict[str, float] = {}

    @contextmanager
    def __call__(self, name: str):
        t = time.perf_counter()
        try:
            yield
        finally:
            self.ms[name] = round(self.ms.get(name, 0.0) + (time.perf_counter() - t) * 1000, 1)


def to_pgvector(vec: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"


def run(pool, embedder, reranker, req: Request, user: dict | None) -> Result:
    stage = Stages()
    p = None
    if user:
        with stage("profile"):
            p = prof.cached_profile(pool, user["id"])
    prefs = p.prefs if p else {}
    q = req.q.strip()
    # Explicit request filters win; otherwise the saved preferences apply.
    level = req.level or (infer_level(q) if q else None) or prefs.get("level")
    cities = req.cities or prefs.get("cities") or []
    remote = req.remote or bool(prefs.get("remote"))

    if q:
        mode, keyword_text, rerank_text = "query", q, q
        with stage("embed"):
            qvec = to_pgvector(embedder.query(q)) if req.use_vector else None
    else:
        if p is None or p.resume_vec is None:
            raise NeedsQuery("Type what you're looking for, or upload your resume first.")
        mode, rerank_text = "feed", prof.summary(p)
        keyword_text = " ".join(f'"{s}"' if " " in s else s for s in p.resume_skills[:6])
        qvec = p.resume_vec if req.use_vector else None

    f = Filters(level=level, cities=cities, remote=remote,
                exclude_ids=p.exclude_ids if p else [], new_only=req.new_only,
                hide_unknown_level=req.hide_unknown_level)
    with stage("search"), pool.connection() as conn, conn.cursor() as cur:
        jobs = search(cur, keyword_text, qvec, f, use_keyword=req.use_keyword,
                      use_vector=req.use_vector, limit=FUSED,
                      taste=p.taste if p and req.use_profile else None)
    if req.use_rerank:
        with stage("rerank"):
            jobs = rerank(reranker, rerank_text, jobs)
    if req.use_final:
        with stage("personalise"):
            by_mode = mode == "feed"
            jobs = personalise(
                jobs, p, use_profile=req.use_profile,
                use_fresh=by_mode if req.use_fresh is None else req.use_fresh,
                use_diversity=by_mode if req.use_diversity is None else req.use_diversity,
            )[:req.limit]
    else:  # the eval's "stop after this stage" variants
        jobs = [j | {"final_score": j.get("rerank_score") or j["score"], "parts": {},
                     "reason": ""} for j in jobs[:req.limit]]
    if p and req.log_shown and jobs:
        with stage("log_shown"), pool.connection() as conn, conn.cursor() as cur:
            prof.log_shown(cur, p.user_id, [j["id"] for j in jobs])
    shown_by = p.user_id if p and req.defer_shown and jobs else None
    return Result(jobs=jobs, level=level, mode=mode, timings=stage.ms, shown_by=shown_by)
