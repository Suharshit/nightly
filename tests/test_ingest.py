"""Ingest idempotency against a real Postgres (DATABASE_URL); skipped if none is reachable.

Everything runs inside one transaction that is rolled back, so the DB is left untouched.
"""

import json
from pathlib import Path

import pytest

from worker import ingest
from worker.sources import greenhouse, lever

FIX = Path(__file__).parent / "fixtures"


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


def pairs():
    gh = greenhouse.parse(json.loads((FIX / "greenhouse_razorpaysoftwareprivatelimited.json")
                                     .read_text(encoding="utf-8")), "Razorpay")
    lv = lever.parse(json.loads((FIX / "lever_cred.json").read_text(encoding="utf-8")), "CRED")
    cos = [ingest.Company("Test Razorpay", "greenhouse", "zz-test-gh", "Bengaluru"),
           ingest.Company("Test CRED", "lever", "zz-test-lv", "Bengaluru")]
    return cos, [(cos[0], j) for j in gh] + [(cos[1], j) for j in lv]


def test_second_run_inserts_nothing(cur):
    cos, ps = pairs()
    ingest.upsert_companies(cur, cos)
    cur.execute("delete from jobs where source||external_id = any(%s)",
                ([j.source + j.external_id for _, j in ps],))

    first = ingest.Stats()
    ingest.upsert_jobs(cur, ps, first)
    assert first.inserted == 8 and first.updated == 0

    second = ingest.Stats()
    ingest.upsert_jobs(cur, ps, second)
    assert second.inserted == 0 and second.updated == 0


def test_changed_description_requeues_extraction(cur):
    cos, ps = pairs()
    ingest.upsert_companies(cur, cos)
    ingest.upsert_jobs(cur, ps, ingest.Stats())
    c, j = ps[0]
    cur.execute("update jobs set extraction_status = 'done' where source = %s and external_id = %s",
                (j.source, j.external_id))
    changed = j.model_copy(update={"description_text": j.description_text + " Now with Go."})
    s = ingest.Stats()
    ingest.upsert_jobs(cur, [(c, changed)], s)
    assert s.updated == 1
    cur.execute("select extraction_status from jobs where source = %s and external_id = %s",
                (j.source, j.external_id))
    assert cur.fetchone()[0] == "pending"


def test_norm_title():
    n = ingest.norm_title
    assert n("Backend Engineer (Go) - II") == n("backend engineer go ii")
    assert "c++" in ingest.norm_title("C++ Developer")
