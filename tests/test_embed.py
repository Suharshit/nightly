"""embed.py: text building, the vector literal, and the cosine dedupe against a real Postgres.

The dedupe test runs inside one transaction that is rolled back; it is skipped without a DB.
No model is loaded here: the vectors are written by hand.
"""

import pytest

from worker import embed, ingest


def test_doc_text_order_and_trimming():
    t = embed.doc_text("Backend Engineer", "Razorpay", "Bengaluru", None,
                       ["python", "go"], "  Build   APIs.\n" + "x" * 2000)
    assert t.startswith("Backend Engineer | Razorpay | Bengaluru | python, go | Build APIs. x")
    assert len(t.split(" | ")[-1]) == embed.DESC_CHARS


def test_doc_text_skips_empty_parts():
    assert embed.doc_text("SDE Intern", None, "", "remote", [], None) == "SDE Intern | remote"


def test_to_pgvector():
    v = embed.to_pgvector([0.5] + [0.0] * 383)
    assert v.startswith("[0.500000,0.000000") and v.endswith("]") and v.count(",") == 383
    with pytest.raises(ValueError):
        embed.to_pgvector([1.0, 2.0])


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


def unit(i: int, j: int | None = None, w: float = 0.0) -> str:
    """A unit vector on axis i, optionally tilted toward axis j by weight w."""
    v = [0.0] * embed.DIM
    v[i] = 1.0
    if j is not None:
        v[j] = w
    n = sum(x * x for x in v) ** 0.5
    return embed.to_pgvector([x / n for x in v])


def test_dedupe_marks_same_company_across_sources_only(cur):
    cur.execute("insert into companies (name, ats, slug) values "
                "('ZZ Test Co', 'greenhouse', 'zz-emb-gh'), ('zz test co', 'lever', 'zz-emb-lv'), "
                "('ZZ Other', 'ashby', 'zz-emb-ab') returning id")
    gh, lv, other = (r[0] for r in cur.fetchall())

    def job(company: int, source: str, ext: str, vec: str) -> int:
        cur.execute("insert into jobs (company_id, source, external_id, title, embedding) "
                    "values (%s, %s, %s, 'Backend Engineer', %s::vector) returning id",
                    (company, source, ext, vec))
        return cur.fetchone()[0]

    a = job(gh, "greenhouse", "zz-a", unit(0))
    b = job(lv, "lever", "zz-b", unit(0, 1, 0.1))       # cosine ~0.995 with a, other source
    c = job(gh, "greenhouse", "zz-c", unit(0, 1, -0.3))  # cos 0.96 with a, same source: kept
    d = job(lv, "lever", "zz-d", unit(2))               # different role: kept
    e = job(other, "ashby", "zz-e", unit(0))            # other company: kept

    embed.dedupe(cur)
    cur.execute("select id, canonical_id from jobs where id = any(%s)", ([a, b, c, d, e],))
    got = dict(cur.fetchall())
    assert got == {a: None, b: a, c: None, d: None, e: None}
