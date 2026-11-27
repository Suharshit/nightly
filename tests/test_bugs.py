"""Bug reports: the /bugs route, its validation and rate limit, and the table's SQL."""

import pytest

from api.app import limits, main
from worker import ingest

H = {"Authorization": "Bearer good-token"}          # student@example.com in conftest
USER = "00000000-0000-0000-0000-0000000000aa"


def test_bug_route_saves_anonymous_and_signed_in_reports(api):
    c, pool, _ = api
    pool.fetchone = (7,)
    r = c.post("/bugs", json={"message": "Apply button does nothing", "page": "/feed"},
               headers={"User-Agent": "phone"})
    assert r.status_code == 200 and r.json() == {"id": 7}
    sql, params = pool.executed[-1]
    assert sql == main.SAVE_BUG and params == (None, None, "/feed", "Apply button does nothing",
                                               "phone")
    r = c.post("/bugs", json={"message": "  Chat is slow  ", "email": "me@x.in"}, headers=H)
    assert r.status_code == 200
    assert pool.executed[-1][1][:4] == (USER, "me@x.in", None, "Chat is slow")


def test_bug_route_rejects_bad_input(api):
    c, _, _ = api
    assert c.post("/bugs", json={"message": "hi"}).status_code == 422             # too short
    assert c.post("/bugs", json={"message": "x" * 2001}).status_code == 422
    assert c.post("/bugs", json={"message": "broken page", "email": "nope"}).status_code == 422


def test_bugs_are_rate_limited():
    assert limits.RATES["/bugs"] == 5


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


def test_bug_table_accepts_a_report_and_checks_status(cur):
    cur.execute(main.SAVE_BUG, (None, None, "/feed", "Cards do not load", "ua"))
    (bug_id,) = cur.fetchone()
    cur.execute("select status from bug_reports where id = %s", (bug_id,))
    assert cur.fetchone() == ("open",)
