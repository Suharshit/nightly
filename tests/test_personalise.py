"""Personalisation: score parts, diversity, reasons, taste updates, prefs, feedback SQL, and
the /feedback and /prefs routes. DB tests run in a rolled-back transaction."""

import math
from datetime import UTC, datetime, timedelta

import pytest

from api.app import profile as prof
from api.app.search import personalise as pz
from api.app.search.personalise import Profile
from worker import ingest
from worker.embed import DIM, to_pgvector

NOW = datetime(2026, 11, 27, 12, tzinfo=UTC)


def job(i, company="Acme", **kw):
    return {"id": i, "title": f"Job {i}", "company": company, "company_id": hash(company) % 1000,
            "city": None, "work_mode": None, "remote": False, "seniority": None,
            "min_exp_years": None, "skills": [], "posted_at": None, "seen_at": None,
            "rerank_score": None, "taste_sim": None} | kw


def test_parts():
    assert pz.jaccard(["Python", "SQL"], ["python", "go"]) == pytest.approx(1 / 3)
    assert pz.jaccard([], ["python"]) == 0.0
    assert pz.freshness(NOW, NOW) == 1.0
    assert pz.freshness(NOW - timedelta(days=14), NOW) == pytest.approx(math.exp(-1))
    assert pz.freshness(None, NOW) == 0.0


def test_penalty_rules():
    p = Profile("u", disliked_companies={7},
                prefs={"avoid": {"seniority": ["senior"], "cities": ["Pune"], "companies": [9]}})
    assert pz.penalty(job(1, company_id=7), p) == 1.0
    assert pz.penalty(job(1, company_id=9), p) == 1.0
    assert pz.penalty(job(1, seniority="senior"), p) == 1.0
    assert pz.penalty(job(1, city="Pune"), p) == 1.0
    assert pz.penalty(job(1, city="Noida", seniority="junior", company_id=1), p) == 0.0


def test_score_uses_the_brief_weights():
    p = Profile("u", resume_skills=["python", "sql"], disliked_companies={5})
    j = job(1, company_id=5, skills=["python", "go"], taste_sim=0.5, seen_at=NOW)
    out = pz.score(j, p, NOW, rerank_norm=0.8)
    expected = 1.0 * 0.8 + 0.3 * 0.5 + 0.2 * (1 / 3) + 0.1 * 1.0 - 0.5 * 1.0
    assert out["final_score"] == pytest.approx(expected, abs=1e-4)
    assert out["parts"] == {"taste": 0.5, "skills": 0.3333, "fresh": 1.0, "penalty": 1.0}
    anon = pz.score(j, None, NOW, rerank_norm=0.8)  # no profile: rerank + freshness only
    assert anon["final_score"] == pytest.approx(0.9)


def test_diversify_caps_two_per_company_in_any_five():
    jobs = [job(i, "A") for i in range(4)] + [job(i, "B") for i in range(4, 6)] + [job(6, "C")]
    out = [j["company"] for j in pz.diversify(jobs)]
    for k in range(len(out) - 4):
        window = out[k:k + 5]
        assert max(window.count(c) for c in set(window)) <= 2, out
    assert out[:2] == ["A", "A"]  # best ones still lead
    assert len(out) == len(jobs)


def test_diversify_falls_back_when_one_company_is_left():
    assert [j["id"] for j in pz.diversify([job(i, "A") for i in range(4)])] == [0, 1, 2, 3]


def test_reason_is_built_from_data():
    p = Profile("u", resume_skills=["python", "sql", "go"], prefs={"cities": ["Pune"]})
    j = job(1, skills=["python", "kafka", "sql"], work_mode="remote", seniority="fresher",
            posted_at=NOW - timedelta(days=2))
    assert pz.reason(j, p, NOW) == ("Matches your Python + SQL · Remote · Fresher-friendly · "
                                    "Posted 2 days ago")
    j2 = job(2, city="Pune", min_exp_years=2, posted_at=NOW)
    assert pz.reason(j2, p, NOW) == "In Pune · 2+ yrs · Posted today"
    assert pz.reason(job(3, seniority="intern"), None, NOW) == "Internship"


def test_personalise_orders_by_final_score_and_respects_switch():
    p = Profile("u", disliked_companies={1})
    a = job(1, "Bad Co", company_id=1, rerank_score=0.9)
    b = job(2, "Good Co", company_id=2, rerank_score=0.6)
    assert [j["id"] for j in pz.personalise([a, b], p, NOW)] == [2, 1]
    assert [j["id"] for j in pz.personalise([a, b], p, NOW, use_profile=False)] == [1, 2]


def test_personalise_without_rerank_keeps_fused_order():
    jobs = [job(i, f"C{i}") for i in range(3)]
    assert [j["id"] for j in pz.personalise(jobs, None, NOW)] == [0, 1, 2]


def unit(i: int) -> str:
    v = [0.0] * DIM
    v[i] = 1.0
    return to_pgvector(v)


def test_moved_taste_moves_20_percent_and_normalises():
    first = prof.moved_taste(None, unit(0))
    assert prof._parse(first)[0] == pytest.approx(1.0)
    second = prof._parse(prof.moved_taste(first, unit(1)))
    assert second[0] == pytest.approx(0.8 / math.hypot(0.8, 0.2), abs=1e-5)
    assert math.fsum(x * x for x in second) == pytest.approx(1.0, abs=1e-5)


def test_clean_prefs():
    assert prof.clean_prefs({"cities": [" Pune ", "Pune", ""], "remote": True,
                             "level": "fresher", "junk": 1}) == {
        "cities": ["Pune"], "remote": True, "level": "fresher"}
    for bad in ({"cities": "Pune"}, {"remote": "yes"}, {"level": "senior"}):
        with pytest.raises(ValueError):
            prof.clean_prefs(bad)


def test_summary():
    p = Profile("u", resume_skills=["python", "sql"],
                prefs={"roles": ["backend"], "level": "fresher"})
    assert prof.summary(p) == "backend fresher entry level skills: python, sql"
    assert prof.summary(Profile("u")) == "software engineer"


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


@pytest.fixture
def world(cur):
    """A user and three jobs at two companies, all inside the rolled-back transaction."""
    cur.execute("insert into auth.users (id, email) values (gen_random_uuid(), 'zz@test') "
                "returning id")
    user = {"id": str(cur.fetchone()[0]), "email": "zz@test"}
    cur.execute("insert into companies (name, ats, slug) values ('ZZ P1', 'lever', 'zz-p1'), "
                "('ZZ P2', 'lever', 'zz-p2') returning id")
    c1, c2 = (r[0] for r in cur.fetchall())
    ids = []
    for ext, co, sen, city, vec in [("zz-j1", c1, "senior", "Pune", unit(0)),
                                    ("zz-j2", c1, "junior", "Noida", unit(1)),
                                    ("zz-j3", c2, "junior", "Pune", unit(2))]:
        cur.execute("insert into jobs (company_id, source, external_id, title, seniority, city, "
                    "embedding) values (%s, 'lever', %s, 'ZZ', %s, %s, %s::vector) returning id",
                    (co, ext, sen, city, vec))
        ids.append(cur.fetchone()[0])
    return user, ids, (c1, c2)


def test_feedback_like_dislike_and_profile_load(cur, world):
    user, (j1, j2, j3), (c1, _) = world
    assert prof.load_profile(cur, user["id"]) is None

    assert prof.record_feedback(cur, user, j2, "like") == {"taste": "moved toward this job"}
    changed = prof.record_feedback(cur, user, j1, "dislike", "too_senior")
    assert changed == {"avoid": {"seniority": "senior"}}
    prof.record_feedback(cur, user, j1, "dislike", "too_senior")  # no duplicate in avoid
    prof.record_feedback(cur, user, j1, "dislike", "wrong_location")
    prof.log_shown(cur, user["id"], [j3, j3, j3])

    p = prof.load_profile(cur, user["id"])
    assert prof._parse(p.taste)[1] == pytest.approx(1.0)
    assert p.prefs["avoid"] == {"seniority": ["senior"], "cities": ["Pune"]}
    assert p.disliked_companies == {c1}
    assert sorted(p.exclude_ids) == sorted([j1, j3])  # disliked, and shown 3 times


def test_feedback_rejects_bad_input(cur, world):
    user, (j1, *_), _ = world
    with pytest.raises(ValueError):
        prof.record_feedback(cur, user, j1, "like", "too_senior")  # reasons are for dislikes
    with pytest.raises(ValueError):
        prof.record_feedback(cur, user, j1, "love")
    with pytest.raises(LookupError):
        prof.record_feedback(cur, user, -1, "like")


def test_update_prefs_merges(cur, world):
    user, *_ = world
    assert prof.update_prefs(cur, user, {"cities": ["Pune"], "level": "fresher"}) == {
        "cities": ["Pune"], "level": "fresher"}
    assert prof.update_prefs(cur, user, {"remote": True}) == {
        "cities": ["Pune"], "level": "fresher", "remote": True}


def test_routes_need_sign_in_and_validate(api):
    c, pool, _ = api
    h = {"Authorization": "Bearer good-token"}
    assert c.post("/feedback", json={"job_id": 1, "action": "like"}).status_code == 401
    assert c.post("/feedback", json={"job_id": 1, "action": "love"},
                  headers=h).status_code == 422
    assert c.patch("/prefs", json={"level": "senior"}, headers=h).status_code == 422
    assert c.patch("/prefs", json={"cities": ["Pune"]}).status_code == 401
    assert c.get("/matches", params={"q": "go"},
                 headers={"Authorization": "Bearer nope"}).status_code == 401
