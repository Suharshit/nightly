"""Admins, /stats, the admin chat-cap exemption, and the signup source (ref)."""

import json

import pytest

from api.app import admin as adm
from api.app import main
from worker import ingest

from .test_agent import DB, FakeLLM, answer

H = {"Authorization": "Bearer good-token"}          # student@example.com in conftest


def test_is_admin_reads_admin_emails(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAILS", " Owner@Example.com , second@x.dev ")
    assert adm.admin_emails() == ["owner@example.com", "second@x.dev"]
    assert adm.is_admin({"email": "owner@EXAMPLE.com"})
    assert not adm.is_admin({"email": "student@example.com"}) and not adm.is_admin(None)


def test_stats_route_is_admin_only(api, monkeypatch):
    c, _, _ = api
    monkeypatch.setattr(adm, "stats", lambda cur: {"users": {"signups": 3}})
    assert c.get("/stats").status_code == 401
    monkeypatch.setenv("ADMIN_EMAILS", "owner@example.com")
    assert c.get("/stats", headers=H).status_code == 403
    monkeypatch.setenv("ADMIN_EMAILS", "student@example.com")
    r = c.get("/stats", headers=H)
    assert r.status_code == 200 and r.json() == {"users": {"signups": 3}}


def test_admins_skip_the_chat_cap(api, monkeypatch):
    c, pool, _ = api
    monkeypatch.setenv("ADMIN_EMAILS", "student@example.com")
    main.app.state.llm = FakeLLM([answer({"reply": "ok", "job_ids": []})])
    main.app.state.pool = db = DB()          # any quota row would be read: none is asked for
    try:
        r = c.post("/chat", json={"message": "hi"}, headers=H)
        assert r.status_code == 200
        assert r.json()["chats_left"] == main.CHAT_DAILY_LIMIT - 1
        assert not db.sql("select count(*), min(created_at) from messages")  # never counted
    finally:
        main.app.state.pool = pool


def test_prefs_records_the_signup_source_once(api):
    c, pool, _ = api
    pool.fetchone = ({"ref": "wa_share"},)
    r = c.patch("/prefs", json={"level": "student", "ref": "wa_share"}, headers=H)
    assert r.status_code == 200 and r.json()["prefs"] == {"ref": "wa_share"}
    sql, params = pool.executed[-1]
    assert sql == main.SET_REF and params == ("wa_share", "00000000-0000-0000-0000-0000000000aa")
    assert "not coalesce(prefs, '{}') ? 'ref'" in main.SET_REF        # first source wins
    bad = c.patch("/prefs", json={"ref": "Robert'); drop"}, headers=H)
    assert bad.status_code == 422


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


def _user(cur, email, ref=None) -> str:
    cur.execute("insert into auth.users (id, email) values (gen_random_uuid(), %s) returning id",
                (email,))
    uid = cur.fetchone()[0]
    prefs = json.dumps({"ref": ref} if ref else {})
    cur.execute("insert into profiles (user_id, email, resume_text, prefs) "
                "values (%s, %s, 'cv', %s::jsonb)", (uid, email, prefs))
    return uid


def test_stats_sql_counts_real_users_and_leaves_admins_out(cur, monkeypatch):
    monkeypatch.setenv("ADMIN_EMAILS", "boss@test")
    cur.execute("select count(*) from auth.users")
    before = adm.stats(cur)
    a, b = _user(cur, "a@test", "wa_share"), _user(cur, "b@test")
    boss = _user(cur, "Boss@test", "linkedin")
    for uid, action in [(a, "shown"), (a, "shown"), (a, "like"), (b, "apply_click"),
                        (boss, "like"), (boss, "shown")]:
        cur.execute("insert into interactions (user_id, action) values (%s, %s)", (uid, action))
    cur.execute("insert into messages (user_id, role, content) values "
                "(%s, 'user', 'hi'), (%s, 'user', 'more'), (%s, 'user', 'x')", (a, a, boss))
    after = adm.stats(cur)
    u0, u1 = before["users"], after["users"]
    assert u1["signups"] - u0["signups"] == 2 and u1["with_resume"] - u0["with_resume"] == 2
    assert u1["by_source"].get("wa_share", 0) - u0["by_source"].get("wa_share", 0) == 1
    assert u1["by_source"].get("linkedin", 0) == u0["by_source"].get("linkedin", 0)
    assert u1["active_7d"] - u0["active_7d"] == 2
    f0, f1 = before["feedback"], after["feedback"]
    assert (f1["shown"] - f0["shown"], f1["likes"] - f0["likes"],
            f1["apply_clicks"] - f0["apply_clicks"]) == (2, 1, 1)
    assert after["chat"]["messages"] - before["chat"]["messages"] == 2
    assert after["excludes"] == "admin accounts and deleted accounts"
