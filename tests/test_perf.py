"""The round-trip savings: profile cache, "shown" logged after the response, smaller search."""

from api.app import main
from api.app import profile as prof
from api.app.search import hybrid, pipeline, rerank
from api.app.search.personalise import Profile

USER = "00000000-0000-0000-0000-0000000000aa"
H = {"Authorization": "Bearer good-token"}


class CountingPool:
    def __init__(self):
        self.connections = 0

    def connection(self):
        self.connections += 1
        return self

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def cursor(self):
        return self


def test_profile_cache_hits_then_expires_and_forgets(monkeypatch):
    pool, loads = CountingPool(), []
    monkeypatch.setattr(prof, "load_profile", lambda cur, uid: loads.append(uid) or f"p-{uid}")
    clock = [1000.0]
    monkeypatch.setattr(prof.time, "monotonic", lambda: clock[0])
    assert prof.cached_profile(pool, "u1") == "p-u1"
    assert prof.cached_profile(pool, "u1") == "p-u1"
    assert loads == ["u1"] and pool.connections == 1          # second call: no round trip
    clock[0] += prof.PROFILE_TTL + 1
    prof.cached_profile(pool, "u1")
    assert loads == ["u1", "u1"]                               # expired: loaded again
    prof.forget_profile("u1")
    prof.cached_profile(pool, "u1")
    assert loads == ["u1", "u1", "u1"]                         # forgotten: loaded again


def test_writes_forget_the_cached_profile(monkeypatch):
    forgot = []
    monkeypatch.setattr(prof, "forget_profile", forgot.append)

    class Cur:
        def execute(self, *a):
            pass

        def fetchone(self):
            return ({},)

    prof.update_prefs(Cur(), {"id": "u2"}, {"remote": True})
    try:
        prof.record_feedback(Cur(), {"id": "u3"}, 999, "like")
    except Exception:
        pass                                   # the fake has no job; forgetting comes first
    assert forgot == ["u2", "u3"]


def test_feed_logs_shown_after_the_response(api, monkeypatch):
    c, pool, _ = api
    p = Profile(user_id=USER, taste=None, resume_vec="[1]", resume_skills=["python"],
                prefs={}, disliked_companies=set(), exclude_ids=[])
    monkeypatch.setattr(prof, "cached_profile", lambda pool, uid: p)
    job = {"id": 7, "title": "Backend Intern", "company": "Acme", "city": "Pune",
           "work_mode": None, "remote": False, "seniority": "intern", "min_exp_years": 0,
           "max_exp_years": 1, "skills": ["python"], "apply_url": None, "posted_at": None,
           "score": 0.03, "keyword_rank": 1, "vector_rank": 1, "company_id": 1,
           "seen_at": None, "taste_sim": None, "snippet": "x"}
    monkeypatch.setattr(pipeline, "search", lambda *a, **k: [dict(job)])
    r = c.get("/matches", headers=H)
    assert r.status_code == 200 and [j["id"] for j in r.json()["jobs"]] == [7]
    assert "log_shown" not in r.json()["timings"]               # not timed inside the request
    shown = [p for s, p in pool.executed if "'shown'" in s]
    assert shown == [(USER, [7])]                               # but logged once, afterwards


def test_search_sql_cuts_to_the_limit_and_short_snippets():
    sql = hybrid.candidates_sql("true", True, True)
    assert "limit %(limit)s" in sql and "left(j.description_text, %(snippet_chars)s)" in sql
    assert hybrid.SNIPPET_CHARS == rerank.JOB_CHARS           # no more than the reranker reads


def test_search_scores_from_stored_ranks():
    rows = [  # already cut to the top rows by SQL; positions are not ranks
        {"id": 1, "keyword_rank": 5, "vector_rank": None},
        {"id": 2, "keyword_rank": None, "vector_rank": 1},
        {"id": 3, "keyword_rank": 2, "vector_rank": 40},
    ]

    class Cur:
        description = [type("C", (), {"name": k})() for k in ("id", "keyword_rank", "vector_rank")]

        def execute(self, sql, params):
            assert params["limit"] == 2 and params["rrf_k"] == hybrid.RRF_K

        def fetchall(self):
            return [tuple(r.values()) for r in rows]

    got = hybrid.search(Cur(), "go", "[1]", hybrid.Filters(), limit=2)
    k = hybrid.RRF_K
    assert [j["id"] for j in got] == [3, 2]
    assert got[0]["score"] == round(1 / (k + 2) + 1 / (k + 40), 5)
    assert main.app  # imported for the route test above
