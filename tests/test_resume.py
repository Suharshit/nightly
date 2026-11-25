"""Resume upload: PDF parsing, skills, the auth check, the /resume and /me routes, and the
profile upsert against a real Postgres (rolled back)."""

import httpx
import pytest
from fastapi import HTTPException

from api.app import auth, resume
from api.app.main import SAVE_RESUME
from worker import ingest
from worker.embed import DIM, to_pgvector

RESUME = ("Asha Rao. B.Tech Computer Science 2026. Projects: built a REST API in Python "
          "with FastAPI and PostgreSQL, deployed with Docker on AWS. Frontend in React and "
          "TypeScript. Coursework: machine learning, data structures, SQL. Internship: "
          "backend intern at a fintech startup, wrote Kafka consumers in Java.")


def make_pdf(text: str) -> bytes:
    """A minimal one-page text PDF (no PDF library needed in tests)."""
    lines = [text[i:i + 80] for i in range(0, len(text), 80)]
    ops = " ".join(f"({line}) Tj 0 -14 Td" for line in lines)
    content = f"BT /F1 10 Tf 40 760 Td {ops} ET".encode()
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
            b"/Resources << /Font << /F1 5 0 R >> >> >>",
            b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offsets = b"%PDF-1.4\n", []
    for i, obj in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + obj + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % off for off in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1,
                                                                               xref)
    return out


def test_pdf_text_and_skills():
    text = resume.pdf_text(make_pdf(RESUME))
    assert "FastAPI and PostgreSQL" in text
    skills = resume.resume_skills(text)
    assert {"python", "postgresql", "docker", "aws", "react", "kafka", "java"} <= set(skills)
    assert resume.embed_text(skills, text).startswith("Skills: ")


@pytest.mark.parametrize("data,msg", [
    (b"hello", "as a PDF"),
    (b"%PDF-1.4 broken", "couldn't open"),
    (make_pdf("Too short."), "scanned image"),
    (b"%PDF" + b"x" * resume.MAX_BYTES, "over 5 MB"),
], ids=["not-pdf", "broken", "scanned", "too-big"])
def test_pdf_text_rejects_bad_files(data, msg):
    with pytest.raises(resume.ResumeError, match=msg):
        resume.pdf_text(data)


def test_supabase_auth_caches_and_rejects():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.headers["authorization"] == "Bearer ok":
            return httpx.Response(200, json={"id": "u1", "email": "a@b.c"})
        return httpx.Response(401, json={"msg": "bad jwt"})

    a = auth.SupabaseAuth("https://x.supabase.co", "anon",
                          httpx.Client(transport=httpx.MockTransport(handler)))
    assert a.user("ok") == {"id": "u1", "email": "a@b.c"}
    assert a.user("ok")["id"] == "u1" and len(calls) == 1  # second call is cached
    assert calls[0].headers["apikey"] == "anon"
    assert str(calls[0].url) == "https://x.supabase.co/auth/v1/user"
    with pytest.raises(HTTPException) as e:
        a.user("bad")
    assert e.value.status_code == 401


def test_expiry_reads_exp_claim():
    import base64
    import json
    body = base64.urlsafe_b64encode(json.dumps({"exp": 1900000000}).encode()).rstrip(b"=")
    assert auth._expiry(f"h.{body.decode()}.s") == 1900000000
    assert auth._expiry("not-a-jwt") is None


def test_resume_route_saves_profile(api):
    c, pool, embedder = api
    r = c.post("/resume", files={"file": ("cv.pdf", make_pdf(RESUME), "application/pdf")},
               headers={"Authorization": "Bearer good-token"})
    assert r.status_code == 200, r.text
    assert "python" in r.json()["skills"] and r.json()["chars"] > 200
    sql, params = pool.executed[-1]
    assert "insert into profiles" in sql
    assert params["user_id"].endswith("aa") and params["email"] == "student@example.com"
    assert embedder.texts[-1].startswith("Skills: ")


def test_resume_route_needs_sign_in_and_a_pdf(api):
    c, _, _ = api
    pdf = {"file": ("cv.pdf", make_pdf(RESUME), "application/pdf")}
    assert c.post("/resume", files=pdf).status_code == 401
    assert c.post("/resume", files=pdf,
                  headers={"Authorization": "Bearer nope"}).status_code == 401
    r = c.post("/resume", files={"file": ("cv.txt", b"plain text", "text/plain")},
               headers={"Authorization": "Bearer good-token"})
    assert r.status_code == 422 and "PDF" in r.json()["detail"]


def test_me(api):
    c, pool, _ = api
    h = {"Authorization": "Bearer good-token"}
    assert c.get("/me", headers=h).json()["has_resume"] is False
    pool.fetchone = (True, ["python"], {"cities": ["Pune"]})
    assert c.get("/me", headers=h).json() == {"email": "student@example.com",
                                              "has_resume": True, "resume_skills": ["python"],
                                              "prefs": {"cities": ["Pune"]}}


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


def test_save_resume_upserts(cur):
    cur.execute("insert into auth.users (id, email) values (gen_random_uuid(), 'zz@test') "
                "returning id")
    uid = cur.fetchone()[0]
    row = {"user_id": uid, "email": "zz@test", "text": "first",
           "vec": to_pgvector([1.0] + [0.0] * (DIM - 1)), "skills": ["python"]}
    cur.execute(SAVE_RESUME, row)
    cur.execute(SAVE_RESUME, row | {"text": "second", "skills": ["go", "sql"]})
    cur.execute("select resume_text, resume_skills, vector_dims(resume_embedding) "
                "from profiles where user_id = %s", (uid,))
    assert cur.fetchone() == ("second", ["go", "sql"], DIM)
