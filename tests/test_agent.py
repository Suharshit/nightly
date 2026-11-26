"""Agent loop, AgentReply, the guardrail and the tools, with a scripted fake LLM and no DB."""

import json

import pytest
from pydantic import ValidationError

from api.app import main
from api.app.agent import loop, tools
from api.app.agent.llm import LLMError
from api.app.agent.schemas import AgentReply, guard

USER = {"id": "00000000-0000-0000-0000-0000000000aa", "email": "student@example.com"}


class Cur:
    def __init__(self, db):
        self.db = db

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self.db.executed.append((" ".join(sql.split()), params))

    def fetchone(self):
        return self.db.one.pop(0) if self.db.one else None

    def fetchall(self):
        return self.db.all

    def cursor(self):
        return self

    def transaction(self):
        return self


class DB:
    def __init__(self, one=None, all_rows=None):
        self.executed: list = []
        self.one, self.all = list(one or []), all_rows or []

    def connection(self):
        return Cur(self)

    def sql(self, start: str) -> list:
        return [p for s, p in self.executed if s.lower().startswith(start)]


def tool_call(name, args, cid="c1"):
    return {"role": "assistant", "content": None, "tool_calls": [
        {"id": cid, "type": "function",
         "function": {"name": name, "arguments": json.dumps(args)}}]}


def answer(obj):
    return {"role": "assistant", "content": obj if isinstance(obj, str) else json.dumps(obj)}


class FakeLLM:
    model = "openai/gpt-oss-120b"

    def __init__(self, script, model_used=None):
        self.script, self.calls = list(script), []
        self.model_used = model_used or self.model

    def chat(self, messages, tools=None, json_only=False, max_tokens=700):
        self.calls.append({"messages": [dict(m) for m in messages], "tools": tools,
                           "json_only": json_only})
        step = self.script.pop(0) if self.script else answer({"reply": "done"})
        if isinstance(step, Exception):
            raise step
        return step, {"prompt_tokens": 100, "completion_tokens": 20}, self.model_used


CARD = {"id": 7, "title": "Backend Intern", "company": "Acme", "city": "Pune",
        "work_mode": None, "remote": False, "seniority": "intern", "min_exp_years": 0,
        "max_exp_years": 1, "skills": ["python", "sql"], "apply_url": "https://x/7",
        "posted_at": None, "reason": "Internship · Pune"}


@pytest.fixture
def fake_search(monkeypatch):
    """search_jobs returns job 7 and records the arguments it got."""
    got = []

    def run(ctx, name, args):
        got.append((name, json.loads(args) if isinstance(args, str) else args))
        if name == "search_jobs":
            ctx.seen[7] = CARD
            return {"count": 1, "jobs": [tools.brief(CARD)]}, True
        return {"error": "nope"}, False

    monkeypatch.setattr(tools, "run", run)
    return got


# --- AgentReply and the guardrail ------------------------------------------------------

def test_agent_reply_validation():
    r = AgentReply.model_validate_json('{"reply": "hi", "job_ids": [3], "reasons": {"3": "ok"}}')
    assert r.reasons == {3: "ok"} and r.follow_up_chips == []
    with pytest.raises(ValidationError):
        AgentReply.model_validate_json('{"job_ids": [3]}')
    with pytest.raises(ValidationError):
        AgentReply.model_validate_json('{"reply": "", "job_ids": []}')


def test_guard_drops_unseen_ids_caps_at_five_and_fills_reasons():
    seen = {i: {"id": i, "reason": f"data {i}"} for i in range(1, 8)}
    r = AgentReply(reply="x", job_ids=[99, 1, 1, 2, 3, 4, 5, 6], reasons={2: "model words"},
                   follow_up_chips=["a", " ", "b", "c", "d"])
    out, dropped = guard(r, seen)
    assert out.job_ids == [1, 2, 3, 4, 5]
    assert dropped == [99, 6]
    assert out.reasons[1] == "data 1" and out.reasons[2] == "model words"
    assert out.follow_up_chips == ["a", "b", "c"]


def test_parse_accepts_fences_and_reports_errors():
    r, err = loop.parse('```json\n{"reply": "hi", "job_ids": []}\n```')
    assert r.reply == "hi" and err is None
    assert loop.parse("sure! here you go")[1] == "no JSON object found"
    assert loop.parse('{"job_ids": "x"}')[0] is None


# --- the loop --------------------------------------------------------------------------

def test_loop_runs_tools_then_answers_and_drops_invented_jobs(fake_search):
    db = DB()
    llm = FakeLLM([tool_call("search_jobs", {"query": "python backend", "seniority": "student"}),
                   answer({"reply": "Two picks", "job_ids": [7, 4242],
                           "reasons": {"7": "Python + SQL"}, "follow_up_chips": ["Only remote"]})])
    turn = loop.Agent(db, None, None, llm).respond(None, "python internships")
    assert fake_search == [("search_jobs", {"query": "python backend", "seniority": "student"})]
    assert turn.reply.job_ids == [7] and turn.jobs == [CARD]
    assert turn.reply.reasons == {7: "Python + SQL"}
    assert turn.json_valid and "4242" in turn.error
    # The tool result went back to the model, linked to its call id.
    tool_msg = llm.calls[1]["messages"][-1]
    assert tool_msg["role"] == "tool" and tool_msg["tool_call_id"] == "c1"
    (log,) = db.sql("insert into agent_logs")
    assert log[0] is None and log[3] == 200 and log[6] is True   # anon, tokens, json_valid
    assert not db.sql("insert into messages")                    # anonymous: no memory


def test_loop_reasks_once_then_falls_back(fake_search):
    db = DB()
    llm = FakeLLM([answer("Here are some jobs!"), answer('{"job_ids": [7]}')])
    turn = loop.Agent(db, None, None, llm).respond(None, "hi")
    assert llm.calls[1]["json_only"] and "not valid JSON" in llm.calls[1]["messages"][-1]["content"]
    assert not turn.json_valid and turn.reply.reply == loop.SORRY and turn.reply.job_ids == []
    assert "invalid JSON twice" in turn.error
    assert db.sql("insert into agent_logs")[0][6] is False


def test_loop_plain_text_fallback_keeps_the_text(fake_search):
    turn = loop.Agent(DB(), None, None, FakeLLM([answer("No luck."), answer("Still no luck.")])
                      ).respond(None, "hi")
    assert not turn.json_valid and turn.reply.reply == "Still no luck."


def test_loop_stops_after_four_tool_rounds(fake_search):
    llm = FakeLLM([tool_call("search_jobs", {"query": "go"}, f"c{i}") for i in range(4)]
                  + [answer({"reply": "ok", "job_ids": [7]})])
    turn = loop.Agent(DB(), None, None, llm).respond(None, "go jobs")
    assert [c["tools"] is not None for c in llm.calls] == [True] * 4 + [False]
    assert len(turn.tool_calls) == 4 and turn.reply.job_ids == [7]


def test_loop_survives_llm_errors_and_logs_fallback_model(fake_search):
    db = DB()
    turn = loop.Agent(db, None, None, FakeLLM([LLMError("rate limited on both models")])
                      ).respond(None, "hi")
    assert turn.reply.reply == loop.SORRY and "rate limited" in turn.error
    llm = FakeLLM([answer({"reply": "hi"})], model_used="openai/gpt-oss-20b")
    turn = loop.Agent(DB(), None, None, llm).respond(None, "hi")
    assert turn.model == "openai/gpt-oss-20b" and "fallback" in turn.error


def test_signed_in_turn_uses_memory_and_saves_messages(fake_search):
    # Newest first, as the query returns them; the oldest row predates the "shown" field.
    history = [("assistant", "Here you go", {"job_ids": [7], "shown": ["7 Backend Intern @ Acme"]}),
               ("user", "python jobs", None), ("assistant", "Older", {"job_ids": [5]})]
    db = DB(one=[None], all_rows=history)          # no profile row yet; 3 old messages
    llm = FakeLLM([tool_call("search_jobs", {"query": "python"}),
                   answer({"reply": "One more", "job_ids": [7]})])
    loop.Agent(db, None, None, llm).respond(USER, "more like that")
    sent = llm.calls[0]["messages"]
    assert sent[1]["content"].startswith("User profile:")
    # Sent oldest first, with the shown jobs so "the second one" or "the Acme one" resolves.
    assert sent[2]["content"] == "Older\n(jobs shown, in order: 5)"
    assert sent[3] == {"role": "user", "content": "python jobs"}
    assert sent[4]["content"].endswith("(jobs shown, in order: 7 Backend Intern @ Acme)")
    assert sent[-1] == {"role": "user", "content": "more like that"}
    (msgs,) = db.sql("insert into messages")
    assert msgs[1] == "more like that" and msgs[3] == "One more"
    assert json.loads(msgs[4])["job_ids"] == [7]
    assert json.loads(msgs[4])["shown"] == ["7 Backend Intern @ Acme"]
    assert db.sql("insert into interactions")[0][1] == [7]       # logged as shown


# --- tools -----------------------------------------------------------------------------

def test_search_jobs_maps_arguments_and_records_seen(monkeypatch):
    got = {}

    def fake_run(pool, embedder, reranker, req, user):
        got["req"] = req
        job = CARD | {"company": "Acme"}
        return type("R", (), {"jobs": [job], "level": req.level})()

    monkeypatch.setattr(tools.pipeline, "run", fake_run)
    ctx = tools.Context(None, None, None, None)
    out, ok = tools.run(ctx, "search_jobs", json.dumps(
        {"query": "backend", "skills": ["go"], "work_mode": "remote", "seniority": "fresher",
         "limit": 50}))
    assert ok and out["count"] == 1 and out["jobs"][0]["id"] == 7
    assert "apply_url" not in out["jobs"][0]                     # the model never sees URLs
    req = got["req"]
    assert (req.q, req.remote, req.level, req.limit, req.log_shown) == \
        ("backend go", True, "fresher", 5, False)
    assert 7 in ctx.seen


def test_tools_that_save_need_a_signed_in_user():
    ctx = tools.Context(DB(), None, None, None)
    out, ok = tools.run(ctx, "update_prefs", {"field": "remote", "value": True, "op": "set"})
    assert not ok and "sign in" in out["error"]
    out, ok = tools.run(ctx, "record_feedback", {"job_id": 7, "action": "like"})
    assert not ok and "sign in" in out["error"]


def test_bad_tool_calls_come_back_as_errors():
    ctx = tools.Context(DB(), None, None, USER)
    assert "unknown tool" in tools.run(ctx, "delete_everything", {})[0]["error"]
    assert not tools.run(ctx, "get_job", "{not json")[1]
    assert "not active" in tools.run(ctx, "get_job", {"job_id": 5})[0]["error"]


@pytest.mark.parametrize("op,value,new", [
    ("add", "Pune", ["Bengaluru", "Pune"]),
    ("remove", "bengaluru", []),
    ("set", ["Delhi", "Pune"], ["Delhi", "Pune"]),
])
def test_update_prefs_list_ops(op, value, new):
    db = DB(one=[({"cities": ["Bengaluru"]},), ({"cities": new},)])
    out, ok = tools.run(tools.Context(db, None, None, USER), "update_prefs",
                        {"field": "cities", "value": value, "op": op})
    assert ok and out == {"saved": {"cities": new}}
    patch = [p for s, p in db.executed if s.startswith("update profiles set prefs")][0]
    assert json.loads(patch[0]) == {"cities": new}


# --- the route -------------------------------------------------------------------------

def test_chat_route_returns_cards_with_reasons(api, fake_search):
    client, pool, _ = api
    main.app.state.llm = FakeLLM([tool_call("search_jobs", {"query": "python"}),
                                  answer({"reply": "Try this", "job_ids": [7],
                                          "reasons": {"7": "Uses your Python"}})])
    main.app.state.pool = DB()
    r = client.post("/chat", json={"message": "python internship"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["reply"] == "Try this" and body["json_valid"]
    assert [j["id"] for j in body["jobs"]] == [7]
    assert body["jobs"][0]["reason"] == "Uses your Python"
    assert client.post("/chat", json={"message": ""}).status_code == 422
    main.app.state.llm = None
    assert client.post("/chat", json={"message": "hi"}).status_code == 503
    main.app.state.pool = pool


# --- fixes found in the live 5-turn run ------------------------------------------------

def test_malformed_tool_call_is_reasked_without_tools(fake_search):
    from api.app.agent.llm import ToolUseFailed
    llm = FakeLLM([tool_call("get_job", {"job_id": 7}),
                   ToolUseFailed("attempted to call tool 'JSON'"),
                   answer({"reply": "Here it is", "job_ids": []})])
    turn = loop.Agent(DB(), None, None, llm).respond(None, "tell me more about the first one")
    assert llm.calls[2]["tools"] is None and llm.calls[2]["json_only"]
    assert turn.json_valid and turn.reply.reply == "Here it is"
    assert "malformed tool call" in turn.error


def _groq(monkeypatch, handler):
    import httpx

    from api.app.agent import llm as llm_mod
    monkeypatch.setenv("GROQ_API_KEY", "test")
    chat = llm_mod.GroqChat("big", "small")
    chat.client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(llm_mod.time, "sleep", lambda s: None)
    return chat


def _ok(model, left="5000"):
    import httpx
    return httpx.Response(200, headers={"x-ratelimit-remaining-tokens": left,
                                        "x-ratelimit-reset-tokens": "30s"},
                          json={"choices": [{"message": {"content": model}}],
                                "usage": {"total_tokens": 10}})


def test_groq_switches_model_when_tokens_run_short(monkeypatch):
    seen = []

    def handler(req):
        model = json.loads(req.content)["model"]
        seen.append(model)
        return _ok(model, left="100" if model == "big" else "7000")

    chat = _groq(monkeypatch, handler)
    assert chat.chat([{"role": "user", "content": "hi"}])[2] == "big"
    # "big" said only 100 tokens are left this window, so the next call skips the wait.
    assert chat.chat([{"role": "user", "content": "hi"}])[2] == "small"
    assert seen == ["big", "small"]


def test_groq_429_retries_once_then_falls_back(monkeypatch):
    import httpx
    seen = []

    def handler(req):
        model = json.loads(req.content)["model"]
        seen.append(model)
        if model == "big":
            return httpx.Response(429, headers={"retry-after": "2"})
        return _ok(model)

    msg, _, model = _groq(monkeypatch, handler).chat([{"role": "user", "content": "x"}])
    assert seen == ["big", "big", "small"] and model == "small"


def test_groq_tool_use_failed_is_its_own_error(monkeypatch):
    import httpx

    from api.app.agent.llm import ToolUseFailed
    chat = _groq(monkeypatch, lambda req: httpx.Response(
        400, json={"error": {"code": "tool_use_failed"}}))
    with pytest.raises(ToolUseFailed):
        chat.chat([{"role": "user", "content": "x"}], tools=tools.SCHEMAS)


def test_too_senior_on_an_intern_tagged_job_adds_no_avoid_rule():
    from api.app import profile as prof
    db = DB(one=[(None, 3, "intern", "Pune")])
    with db.connection() as cur:
        assert prof.record_feedback(cur, USER, 7, "dislike", "too_senior") == {}
    assert not db.sql("update profiles set prefs")
    db = DB(one=[(None, 3, "senior", "Pune"), ({},)])
    with db.connection() as cur:
        assert prof.record_feedback(cur, USER, 7, "dislike", "too_senior") == \
            {"avoid": {"seniority": "senior"}}
