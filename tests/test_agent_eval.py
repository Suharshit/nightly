"""Agent eval plumbing: argument matching, scoring, the labelling CLI and the table."""

import json

import pytest

from eval import agent_common as ac
from eval import label_agent, run_agent_eval


def call(name, **args):
    return {"name": name, "args": args, "ok": True}


@pytest.mark.parametrize("expected,actual,ok", [
    ("Remote", "remote", True),
    (["pune"], ["Pune", "Delhi"], True),
    (["pune", "goa"], ["Pune"], False),
    ("Pune", ["Pune", "Delhi"], True),       # update_prefs value given as a list
    (True, True, True),
    (True, "true", False),
    (999, "999", True),
    (999, None, False),
])
def test_value_matches(expected, actual, ok):
    assert ac.value_matches(expected, actual) is ok


def test_parse_arg():
    assert ac.parse_arg("int", " 12 ") == 12
    assert ac.parse_arg("list", "go, kafka,") == ["go", "kafka"]
    assert ac.parse_arg("value", "TRUE") is True
    assert ac.parse_arg("value", "Pune, Delhi") == ["Pune", "Delhi"]
    assert ac.parse_arg("value", "student") == "student"
    with pytest.raises(ValueError):
        ac.parse_arg("int", "two")


def test_score_tools_and_args():
    label = {"tools": ["update_prefs", "search_jobs"],
             "args": {"update_prefs": {"field": "remote", "value": True}}}
    good = [call("update_prefs", field="remote", value=True, op="set"),
            call("search_jobs", query="python", work_mode="remote")]
    assert ac.score(label, good) == {"tool_ok": True, "args_ok": True}
    # Right tools, wrong argument.
    bad = [call("update_prefs", field="cities", value=["remote"], op="add"), good[1]]
    assert ac.score(label, bad) == {"tool_ok": True, "args_ok": False}
    # A missing tool fails both.
    assert ac.score(label, good[:1]) == {"tool_ok": False, "args_ok": False}
    # Extra calls are fine; no labelled args means args_ok is None.
    assert ac.score({"tools": ["get_job"], "args": {}},
                    [call("get_job", job_id=1), call("explain_match", job_id=1)]) == \
        {"tool_ok": True, "args_ok": None}


def test_score_expects_no_tool():
    assert ac.score({"tools": [], "args": {}}, [])["tool_ok"] is True
    assert ac.score({"tools": [], "args": {}}, [call("search_jobs")])["tool_ok"] is False


def test_label_cli_writes_resumes_and_skips(tmp_path, monkeypatch, capsys):
    convos, labels = tmp_path / "convos.jsonl", tmp_path / "agent_labels.jsonl"
    convos.write_text("".join(json.dumps(c) + "\n" for c in [
        {"id": "a01", "message": "only remote from now on", "prefs": {}, "history": []},
        {"id": "a02", "message": "hi", "prefs": {}, "history": []},
        {"id": "a03", "message": "tell me more", "prefs": {},
         "history": [{"role": "assistant", "content": "x", "shown": ["7 Dev @ Acme"]}]},
    ]), encoding="utf-8")
    for mod in (ac, label_agent):
        monkeypatch.setattr(mod, "CONVOS", convos, raising=False)
        monkeypatch.setattr(mod, "AGENT_LABELS", labels, raising=False)
    # a01: tools 3,1 with update_prefs field/value/op, search_jobs work_mode; a02: no tool;
    # a03: skip, then quit is not needed because the list ends.
    answers = iter(["3,1", "remote", "true", "set", "", "remote", "", "", "0", "s"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    label_agent.label(None)
    got = ac.load_agent_labels()
    assert got["a01"] == {"id": "a01", "tools": ["update_prefs", "search_jobs"],
                          "args": {"update_prefs": {"field": "remote", "value": True,
                                                    "op": "set"},
                                   "search_jobs": {"work_mode": "remote"}}}
    assert got["a02"] == {"id": "a02", "tools": [], "args": {}}
    assert "a03" not in got
    assert "7 Dev @ Acme" in capsys.readouterr().out
    # Resuming shows only a03; q saves nothing more.
    answers = iter(["q"])
    label_agent.label(None)
    assert set(ac.load_agent_labels()) == {"a01", "a02"}


def test_summary_and_table():
    labels = {"a1": {"tools": ["search_jobs"], "args": {"search_jobs": {"work_mode": "remote"}}},
              "a2": {"tools": [], "args": {}}}
    runs = [
        {"id": "a1", "model": "m", "calls": [call("search_jobs", work_mode="remote")],
         "json_valid": True, "dropped": [], "latency_ms": 1000, "usage": {"prompt_tokens": 2000}},
        {"id": "a2", "model": "m", "calls": [call("search_jobs")], "json_valid": False,
         "dropped": [42], "latency_ms": 3000, "usage": {"prompt_tokens": 1000}},
    ]
    (row,) = run_agent_eval.summarise(runs, labels)
    assert row["tool_acc"] == 0.5 and row["arg_acc"] == 1.0 and row["arg_turns"] == 1
    assert row["json_valid"] == 0.5 and row["hallucinated"] == 0.5
    assert row["p50_ms"] == 2000 and row["p95_ms"] == 3000 and row["prompt_tokens"] == 1500
    text = run_agent_eval.table([row])
    assert "| m | 50% | 100% (1) | 50% | 50% | 2000 | 3000 | 1500 |" in text


def test_pct_nearest_rank():
    assert run_agent_eval.pct(list(range(1, 21)), 0.95) == 19
    assert run_agent_eval.pct([5], 0.95) == 5
    assert run_agent_eval.pct([], 0.5) == 0.0


def test_proposed_convos_have_no_expected_answers():
    """The proposed turns carry no labels: those come only from the owner."""
    cases = ac.load_cases()
    assert len(cases) >= 30 and len({c["id"] for c in cases}) == len(cases)
    for c in cases:
        assert set(c) == {"id", "message", "prefs", "history"}
