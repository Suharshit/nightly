"""Reranking: the job text, ordering by cross-encoder score, and /matches wiring."""

import pytest

from api.app import main
from api.app.search import pipeline, rerank
from api.app.search.hybrid import FUSED
from tests.conftest import FakeReranker


def job(i, title, **kw):
    return {"id": i, "title": title, "company": "Acme", "city": None, "work_mode": None,
            "remote": False, "seniority": None, "min_exp_years": None, "max_exp_years": None,
            "skills": [], "apply_url": None, "posted_at": None, "score": 0.01,
            "keyword_rank": None, "vector_rank": None} | kw


def test_job_text_is_short_and_ordered():
    t = rerank.job_text(job(1, "Frontend Intern", remote=True, work_mode="remote",
                            skills=["react", "css"], snippet="  Build  UI. " + "y" * 900))
    assert t.startswith("Frontend Intern | Acme | remote | remote | react, css | Build UI. y")
    assert len(t.split(" | ")[-1]) == rerank.JOB_CHARS


def test_rerank_orders_by_score_and_keeps_ties_stable():
    jobs = [job(1, "Product Management Intern"), job(2, "Frontend React Intern"),
            job(3, "Talent Acquisition Intern"), job(4, "Product Design Intern")]
    out = rerank.rerank(FakeReranker(), "frontend react intern", jobs)
    assert [j["id"] for j in out] == [2, 1, 3, 4]  # 1, 3, 4 tie: fused order kept
    assert all(0 < j["rerank_score"] < 1 for j in out)
    assert out[0]["rerank_score"] == pytest.approx(rerank.sigmoid(2.0), abs=1e-5)


def test_rerank_empty():
    r = FakeReranker()
    assert rerank.rerank(r, "q", []) == [] and r.calls == []


@pytest.fixture
def seen(api, monkeypatch):
    calls = {}
    fused = [job(1, "Product Management Intern"), job(2, "Frontend React Intern")]

    def fake_search(cur, q, qvec, f, **kw):
        calls.update(kw)
        return fused[:kw["limit"]]

    monkeypatch.setattr(pipeline, "search", fake_search)
    return api[0], calls


def test_matches_reranks_the_full_fused_list(seen):
    c, calls = seen
    body = c.get("/matches", params={"q": "frontend react intern", "limit": 1}).json()
    assert calls["limit"] == FUSED  # fetch 30, rerank, then cut to 1
    assert [j["id"] for j in body["jobs"]] == [2] and body["jobs"][0]["rerank_score"] > 0.5
    assert main.app.state.reranker.calls[-1][0] == "frontend react intern"


def test_matches_rerank_can_be_switched_off(seen):
    c, calls = seen
    body = c.get("/matches", params={"q": "frontend react intern", "limit": 1,
                                     "rerank": "false"}).json()
    assert calls["limit"] == FUSED
    assert [j["id"] for j in body["jobs"]] == [1] and body["jobs"][0]["rerank_score"] is None
