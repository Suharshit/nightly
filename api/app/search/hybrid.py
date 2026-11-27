"""Hybrid retrieval: hard filter -> keyword top 50 + vector top 50 -> reciprocal rank fusion.

Reranking and personalisation sit on top of this (Fri). Each retriever can be switched off
so the search eval can compare variants.
"""

import re
from dataclasses import dataclass, field

RRF_K = 60
SNIPPET_CHARS = 200        # the reranker reads this much of the description (rerank.JOB_CHARS)
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
    new_only: bool = False        # only jobs first seen in the latest nightly ingest run


# Jobs the latest ingest run added: first_seen is set when a job is first inserted.
NEW_SINCE_LAST_RUN = "j.first_seen >= (select max(started_at) from ingest_runs)"


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
    if f.new_only:
        sql.append(NEW_SINCE_LAST_RUN)
    return " and ".join(sql), params


def or_query(q: str) -> str:
    """Terms joined with OR for websearch_to_tsquery, so a job matching 2 of 3 words still
    ranks (plain websearch syntax ANDs every word, which empties short queries).
    Quoted phrases and -exclusions are kept as written."""
    parts = re.findall(r'-?"[^"]+"|\S+', q)
    return " or ".join(p for p in parts if p.lower() != "or")


# Both retrievers and the job details in one round trip: the API host and Supabase are far
# apart, so three queries cost ~3x the network latency. Ranks are 1-based; RRF is in Python.
KEYWORD_CTE = """kw as (
  select id, row_number() over (order by rank desc, id) as r from (
    select j.id, ts_rank_cd(j.tsv, q) as rank
    from jobs j, websearch_to_tsquery('english', %(tsq)s) q
    where {cond} and j.tsv @@ q
    order by rank desc, j.id limit %(k)s) s)"""

VECTOR_CTE = """vec as (
  select id, row_number() over (order by d, id) as r from (
    select j.id, j.embedding <=> %(qvec)s::vector as d from jobs j
    where {cond} and j.embedding is not null
    order by d, j.id limit %(k)s) s)"""

EMPTY_CTE = "{name} as (select null::bigint as id, null::bigint as r where false)"

CANDIDATES = """with {kw}, {vec}
select j.id, j.title, c.name as company, j.city, j.work_mode, j.remote, j.seniority,
       j.min_exp_years, j.max_exp_years, j.skills, j.apply_url, j.posted_at,
       left(j.description_text, %(snippet_chars)s) as snippet,
       kw.r as keyword_rank, vec.r as vector_rank,
       j.company_id, coalesce(j.posted_at, j.first_seen) as seen_at,
       case when %(taste)s::vector is null then null
            else 1 - (j.embedding <=> %(taste)s::vector) end as taste_sim
from jobs j join companies c on c.id = j.company_id
left join kw on kw.id = j.id left join vec on vec.id = j.id
where kw.id is not null or vec.id is not null
-- Fuse in SQL too, so only the `limit` best rows cross the network (the API is far from the
-- database: each round trip is ~200 ms, and 100 rows took more than one).
order by coalesce(1.0 / (%(rrf_k)s + kw.r), 0) + coalesce(1.0 / (%(rrf_k)s + vec.r), 0) desc,
         kw.r nulls last, vec.r
limit %(limit)s"""


def candidates_sql(cond: str, use_keyword: bool, use_vector: bool) -> str:
    kw = KEYWORD_CTE.format(cond=cond) if use_keyword else EMPTY_CTE.format(name="kw")
    vec = VECTOR_CTE.format(cond=cond) if use_vector else EMPTY_CTE.format(name="vec")
    return CANDIDATES.format(kw=kw, vec=vec)


def rrf(*ranked: list[int], k: int = RRF_K) -> list[tuple[int, float]]:
    """Reciprocal rank fusion: score(d) = sum over lists of 1 / (k + rank), rank from 1.
    Ties keep the order in which ids were first seen, so results are deterministic."""
    scores: dict[int, float] = {}
    for ids in ranked:
        for rank, doc in enumerate(ids, 1):
            scores[doc] = scores.get(doc, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda kv: -kv[1])


def search(cur, q: str, qvec: str | None, f: Filters, *, use_keyword: bool = True,
           use_vector: bool = True, limit: int = FUSED, taste: str | None = None) -> list[dict]:
    """Returns up to `limit` jobs, best first, each with its fused score and both ranks."""
    use_keyword = use_keyword and bool(q.strip())
    use_vector = use_vector and qvec is not None
    if not (use_keyword or use_vector):
        return []
    cond, params = where(f)
    params |= {"k": PER_RETRIEVER, "tsq": or_query(q), "qvec": qvec, "taste": taste,
               "rrf_k": RRF_K, "limit": limit, "snippet_chars": SNIPPET_CHARS}
    cur.execute(candidates_sql(cond, use_keyword, use_vector), params)
    cols = [c.name for c in cur.description]
    rows = [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]
    # Score from each retriever's own rank (the rows are already cut to `limit`, so list
    # positions are not ranks). Ties: keyword-ranked first, then by rank, as rrf() orders them.
    for row in rows:
        row["score"] = sum(1.0 / (RRF_K + r) for r in (row["keyword_rank"], row["vector_rank"])
                           if r is not None)
    rows.sort(key=lambda r: (-r["score"], r["keyword_rank"] is None,
                             r["keyword_rank"] or 0, r["vector_rank"] or 0))
    return [r | {"score": round(r["score"], 5)} for r in rows[:limit]]
