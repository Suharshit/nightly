"""Hybrid retrieval: hard filter -> keyword top 50 + vector top 50 -> reciprocal rank fusion.

Reranking and personalisation sit on top of this (Fri). Each retriever can be switched off
so the search eval can compare variants.
"""

import re
from dataclasses import dataclass, field

RRF_K = 60
PER_RETRIEVER = 50
FUSED = 30

# The onboarding chips. Each level allows these seniorities (plus unknown) and at most
# this many required years. "A fresher never sees senior."
LEVELS: dict[str, tuple[tuple[str, ...], int]] = {
    "student": (("intern", "fresher"), 0),
    "fresher": (("intern", "fresher", "junior"), 1),
    "junior": (("fresher", "junior"), 2),
}
_LEVEL_WORDS = [
    ("student", re.compile(r"\b(intern|internship|student)s?\b", re.I)),
    ("fresher", re.compile(r"\b(fresher|freshers|entry[- ]level|new grad|graduate|0-1 years?)\b",
                           re.I)),
]


def infer_level(q: str) -> str | None:
    """A level word in the query acts as the level filter when none was given."""
    for level, pattern in _LEVEL_WORDS:
        if pattern.search(q):
            return level
    return None


@dataclass
class Filters:
    level: str | None = None
    cities: list[str] = field(default_factory=list)
    remote: bool = False          # with cities: those cities OR remote; alone: remote only
    exclude_ids: list[int] = field(default_factory=list)


def where(f: Filters) -> tuple[str, dict]:
    """The hard filter as SQL. Only active, canonical rows are ever returned."""
    sql = ["j.is_active", "j.canonical_id is null"]
    params: dict = {}
    if f.level:
        allowed, max_years = LEVELS[f.level]
        sql.append("(j.seniority is null or j.seniority = any(%(seniorities)s))")
        sql.append("(j.min_exp_years is null or j.min_exp_years <= %(max_years)s)")
        params |= {"seniorities": list(allowed), "max_years": max_years}
    place = []
    if f.cities:
        place.append("j.city = any(%(cities)s)")
        params["cities"] = f.cities
    if f.remote:
        place.append("j.work_mode = 'remote' or j.remote")
    if place:
        sql.append("(" + " or ".join(place) + ")")
    if f.exclude_ids:
        sql.append("not (j.id = any(%(exclude)s))")
        params["exclude"] = f.exclude_ids
    return " and ".join(sql), params


def or_query(q: str) -> str:
    """Terms joined with OR for websearch_to_tsquery, so a job matching 2 of 3 words still
    ranks (plain websearch syntax ANDs every word, which empties short queries).
    Quoted phrases and -exclusions are kept as written."""
    parts = re.findall(r'-?"[^"]+"|\S+', q)
    return " or ".join(p for p in parts if p.lower() != "or")


def keyword_sql(cond: str) -> str:
    return f"""
select j.id from jobs j, websearch_to_tsquery('english', %(tsq)s) q
where {cond} and j.tsv @@ q
order by ts_rank_cd(j.tsv, q) desc, j.id limit %(k)s"""


def vector_sql(cond: str) -> str:
    return f"""
select j.id from jobs j
where {cond} and j.embedding is not null
order by j.embedding <=> %(qvec)s::vector, j.id limit %(k)s"""


def rrf(*ranked: list[int], k: int = RRF_K) -> list[tuple[int, float]]:
    """Reciprocal rank fusion: score(d) = sum over lists of 1 / (k + rank), rank from 1.
    Ties keep the order in which ids were first seen, so results are deterministic."""
    scores: dict[int, float] = {}
    for ids in ranked:
        for rank, doc in enumerate(ids, 1):
            scores[doc] = scores.get(doc, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda kv: -kv[1])


DETAILS = """
select j.id, j.title, c.name as company, j.city, j.work_mode, j.remote, j.seniority,
       j.min_exp_years, j.max_exp_years, j.skills, j.apply_url, j.posted_at
from jobs j join companies c on c.id = j.company_id
where j.id = any(%(ids)s)"""


def search(cur, q: str, qvec: str | None, f: Filters, *, use_keyword: bool = True,
           use_vector: bool = True, limit: int = FUSED) -> list[dict]:
    """Returns up to `limit` jobs, best first, each with its fused score and both ranks."""
    cond, params = where(f)
    params["k"] = PER_RETRIEVER
    kw: list[int] = []
    vec: list[int] = []
    if use_keyword and q.strip():
        cur.execute(keyword_sql(cond), params | {"tsq": or_query(q)})
        kw = [r[0] for r in cur.fetchall()]
    if use_vector and qvec is not None:
        cur.execute(vector_sql(cond), params | {"qvec": qvec})
        vec = [r[0] for r in cur.fetchall()]
    fused = rrf(kw, vec)[:limit]
    if not fused:
        return []
    cur.execute(DETAILS, {"ids": [d for d, _ in fused]})
    cols = [c.name for c in cur.description]
    rows = {r[0]: dict(zip(cols, r, strict=True)) for r in cur.fetchall()}
    kw_rank = {d: i for i, d in enumerate(kw, 1)}
    vec_rank = {d: i for i, d in enumerate(vec, 1)}
    return [rows[d] | {"score": round(s, 5), "keyword_rank": kw_rank.get(d),
                       "vector_rank": vec_rank.get(d)}
            for d, s in fused if d in rows]
