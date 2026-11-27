"""Delete my data: the route, and that the SQL really removes every row for one user only."""

import pytest

from api.app import main
from api.app.auth import SupabaseAuth
from api.app.main import DELETE_USER
from worker import ingest

USER = "00000000-0000-0000-0000-0000000000aa"


def test_delete_me_route(api):
    c, pool, _ = api
    assert c.delete("/me").status_code == 401
    r = c.delete("/me", headers={"Authorization": "Bearer good-token"})
    assert r.status_code == 200 and r.json() == {"deleted": True}
    sqls = [(sql, params) for sql, params in pool.executed]
    assert [s for s, _ in sqls] == DELETE_USER
    assert all(p == {"id": USER} for _, p in sqls)
    assert main.app.state.auth.forgotten == [USER]


def test_forget_drops_only_that_users_tokens():
    auth = SupabaseAuth(url="https://x.supabase.co", anon_key="k")
    auth.cache = {"t1": (9e12, {"id": "a"}), "t2": (9e12, {"id": "a"}), "t3": (9e12, {"id": "b"})}
    auth.forget("a")
    assert list(auth.cache) == ["t3"]


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


def _user_with_data(cur, email: str) -> str:
    cur.execute("insert into auth.users (id, email) values (gen_random_uuid(), %s) returning id",
                (email,))
    uid = cur.fetchone()[0]
    cur.execute("insert into profiles (user_id, email, resume_text) values (%s, %s, 'cv')",
                (uid, email))
    cur.execute("insert into interactions (user_id, action) values (%s, 'shown')", (uid,))
    cur.execute("insert into messages (user_id, role, content) values (%s, 'user', 'hi')", (uid,))
    cur.execute("insert into agent_logs (user_id, model) values (%s, 'm')", (uid,))
    return uid


def _rows(cur, uid) -> dict[str, int]:
    counts = {}
    for table, col in [("auth.users", "id"), ("profiles", "user_id"),
                       ("interactions", "user_id"), ("messages", "user_id"),
                       ("agent_logs", "user_id")]:
        cur.execute(f"select count(*) from {table} where {col} = %s", (uid,))
        counts[table] = cur.fetchone()[0]
    return counts


def test_delete_sql_removes_everything_for_one_user(cur):
    gone, kept = _user_with_data(cur, "gone@test"), _user_with_data(cur, "kept@test")
    for sql in DELETE_USER:
        cur.execute(sql, {"id": gone})
    assert set(_rows(cur, gone).values()) == {0}
    assert set(_rows(cur, kept).values()) == {1}
