"""Hybrid search: RRF, query helpers, the hard filter, and search() on a real Postgres.

DB tests run inside a transaction that is rolled back; skipped without a database.
The query vector is written by hand, so no model is loaded.
"""

import pytest

from api.app.search import hybrid, pipeline
from worker import ingest
from worker.embed import DIM, to_pgvector


def test_rrf_sums_reciprocal_ranks():
    fused = dict(hybrid.rrf([1, 2, 3], [3, 4]))
    assert fused[3] == pytest.approx(1 / 63 + 1 / 61)
    assert fused[1] == pytest.approx(1 / 61)
    assert list(dict(hybrid.rrf([1, 2, 3], [3, 4]))) == [3, 1, 2, 4]  # in both lists wins


def test_rrf_ties_keep_first_seen_order_and_handles_empty():
    assert [d for d, _ in hybrid.rrf([5], [6])] == [5, 6]
    assert hybrid.rrf([], []) == []


def test_or_query_keeps_phrases_and_exclusions():
    assert hybrid.or_query('python  backend') == "python or backend"
    assert hybrid.or_query('"react native" -senior or go') == '"react native" or -senior or go'


@pytest.mark.parametrize("q,level", [
    ("python backend fresher", "fresher"), ("Entry-level data analyst", "fresher"),
    ("frontend internship", "student"), ("senior go engineer", None)])
def test_infer_level(q, level):
    assert hybrid.infer_level(q) == level


def test_where_combines_filters():
    sql, params = hybrid.where(hybrid.Filters(level="fresher", cities=["Pune"], remote=True))
    assert "j.canonical_id is null" in sql and "j.city = any(%(cities)s) or j.work_mode" in sql
    assert params == {"seniorities": ["intern", "fresher", "junior"], "max_years": 1,
                      "cities": ["Pune"]}


@pytest.fixture
def cur():
    try:
        conn = ingest.connect()
    except Exception:
        pytest.skip("no database")
    with conn.cursor() as c:
        yield c
    conn.rollback()
    conn.close()


def axis(i: int) -> str:
    v = [0.0] * DIM
    v[i] = 1.0
    return to_pgvector(v)


def test_search_filters_and_fuses(cur):
    cur.execute("insert into companies (name, ats, slug) values ('ZZ Search Co', 'greenhouse', "
                "'zz-search') returning id")
    co = cur.fetchone()[0]

    def job(ext, title, seniority, vec, canonical=None, city="Pune", exp=None):
        cur.execute("""insert into jobs (company_id, source, external_id, title, seniority,
                         min_exp_years, city, embedding, canonical_id, description_text)
                       values (%s, 'greenhouse', %s, %s, %s, %s, %s, %s::vector, %s, 'zzqx')
                       returning id""", (co, ext, title, seniority, exp, city, vec, canonical))
        return cur.fetchone()[0]

    both = job("zz-1", "Zzqlang Backend Engineer", "junior", axis(7))
    kw_only = job("zz-2", "Zzqlang Developer", "fresher", axis(100))
    senior = job("zz-3", "Zzqlang Backend Engineer", "senior", axis(7))
    too_much_exp = job("zz-4", "Zzqlang Backend Engineer", None, axis(7), exp=3)
    dupe = job("zz-5", "Zzqlang Backend Engineer", "junior", axis(7), canonical=both)
    other_city = job("zz-6", "Zzqlang Backend Engineer", "junior", axis(7), city="Chennai")

    f = hybrid.Filters(level="fresher", cities=["Pune"])
    got = hybrid.search(cur, "zzqlang backend", axis(7), f)
    ids = [j["id"] for j in got]
    assert ids[0] == both and both in ids and kw_only in ids
    assert not {senior, too_much_exp, dupe, other_city} & set(ids)
    top = got[0]
    assert top["keyword_rank"] == 1 and top["vector_rank"] == 1
    assert top["company"] == "ZZ Search Co"

    # Each retriever can be switched off for the eval.
    no_kw = hybrid.search(cur, "zzqlang backend", axis(7), f, use_keyword=False)
    assert all(j["keyword_rank"] is None for j in no_kw)
    no_vec = hybrid.search(cur, "zzqlang backend", None, f)
    assert {j["id"] for j in no_vec} == {both, kw_only}


@pytest.fixture
def client(api, monkeypatch):
    c, _, _ = api
    seen = {}

    def fake_search(cur, q, qvec, f, **kw):
        seen.update(q=q, qvec=qvec, f=f, **kw)
        return [{"id": 1, "title": "Backend Engineer", "company": "Acme", "city": "Pune",
                 "work_mode": "remote", "remote": True, "seniority": "junior",
                 "min_exp_years": 0, "max_exp_years": 1, "skills": ["python"],
                 "apply_url": "https://example.com/1", "posted_at": None, "score": 0.03,
                 "keyword_rank": 1, "vector_rank": 2}]

    monkeypatch.setattr(pipeline, "search", fake_search)
    return c, seen


def test_matches_infers_level_and_passes_filters(client):
    c, seen = client
    r = c.get("/matches", params={"q": "python backend fresher", "city": ["Pune", "Remote"],
                                  "remote": "true"})
    assert r.status_code == 200
    body = r.json()
    assert body["level"] == "fresher" and body["count"] == 1 and body["jobs"][0]["id"] == 1
    assert seen["f"].cities == ["Pune", "Remote"] and seen["f"].remote is True
    assert seen["qvec"].startswith("[0.000000")


def test_matches_new_passes_new_only(client):
    c, seen = client
    assert c.get("/matches", params={"q": "python"}).status_code == 200
    assert seen["f"].new_only is False
    assert c.get("/matches", params={"q": "python", "new": "true"}).status_code == 200
    assert seen["f"].new_only is True


def test_where_new_only_keeps_last_runs_jobs():
    sql, _ = hybrid.where(hybrid.Filters(new_only=True))
    assert hybrid.NEW_SINCE_LAST_RUN in sql
    assert hybrid.NEW_SINCE_LAST_RUN not in hybrid.where(hybrid.Filters())[0]


def test_new_only_returns_jobs_first_seen_in_the_latest_run(cur):
    cur.execute("insert into companies (name, ats, slug) values ('ZZ New Co', 'greenhouse', "
                "'zz-new') returning id")
    co = cur.fetchone()[0]
    # Two runs in the future, so real rows in the table never count as "new" here.
    cur.execute("insert into ingest_runs (started_at, finished_at) values "
                "(now() + interval '1 day', now() + interval '1 day'), "
                "(now() + interval '2 days', now() + interval '2 days')")

    def job(ext, first_seen):
        cur.execute("""insert into jobs (company_id, source, external_id, title, embedding,
                         description_text, first_seen)
                       values (%s, 'greenhouse', %s, 'Zzqnew Backend Engineer', %s::vector,
                               'zzqnew', now() + %s::interval) returning id""",
                    (co, ext, axis(9), first_seen))
        return cur.fetchone()[0]

    old = job("zz-new-1", "1 day 1 hour")       # before the latest run
    new = job("zz-new-2", "2 days 1 hour")      # added by the latest run
    every = hybrid.search(cur, "zzqnew backend", axis(9), hybrid.Filters())
    fresh = hybrid.search(cur, "zzqnew backend", axis(9), hybrid.Filters(new_only=True))
    assert {old, new} <= {j["id"] for j in every}
    assert [j["id"] for j in fresh] == [new]


def test_matches_validates_input(client):
    c, _ = client
    assert c.get("/matches", params={"q": ""}).status_code == 400  # no query, no resume
    assert c.get("/matches", params={"q": "go", "level": "senior"}).status_code == 422
    assert c.get("/health").json() == {"ok": True}
