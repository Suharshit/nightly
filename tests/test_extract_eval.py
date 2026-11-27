"""Extraction eval: normalisation, per-field scoring, the results table, and the frozen sample."""

import builtins

import pytest

from eval import extract_common as ec
from eval import label_extract, run_extract_eval


def test_norm_treats_blank_as_not_stated_and_canonicalises():
    assert ec.norm("seniority", "") is None and ec.norm("seniority", None) is None
    assert ec.norm("city", "bangalore") == "Bengaluru" == ec.norm("city", "Bengaluru")
    assert ec.norm("city", "gurgaon") == "Gurugram"
    assert ec.norm("city", "zurich") == "Zurich"
    assert ec.norm("min_exp_years", "3") == 3
    assert ec.norm("work_mode", "Remote ") == "remote"


def _row(job_id, source, **pred):
    base = {f: None for f in ec.FIELDS} | {"skills": ["python", "sql", "excel"]}
    return {"job_id": job_id, "source": source, "pred": base | pred}


SAMPLE = [
    _row(1, "rules", seniority="junior", min_exp_years=1, city="Bengaluru"),
    _row(2, "rules+llm:qwen2.5:3b", seniority="senior", min_exp_years=5, work_mode="remote"),
    _row(3, "rules", seniority="intern"),            # not labelled: ignored
]
LABELS = {
    1: {"job_id": 1, "fields": {"seniority": "junior", "min_exp_years": 2, "max_exp_years": None,
                                "work_mode": None, "city": "bangalore", "employment_type": None},
        "skills_wrong": ["excel"], "skills_missing": ["django"]},
    2: {"job_id": 2, "fields": {"seniority": "mid", "min_exp_years": 5, "max_exp_years": None,
                                "work_mode": "remote", "city": None, "employment_type": None},
        "skills_wrong": [], "skills_missing": []},
}


def test_score_counts_matches_per_field_and_group():
    s = ec.score(SAMPLE, LABELS)
    assert s["all"]["jobs"] == 2 and s["rules only"]["jobs"] == 1 and s["rules + LLM"]["jobs"] == 1
    assert s["all"]["fields"]["seniority"] == [1, 2]
    assert s["all"]["fields"]["min_exp_years"] == [1, 2]
    assert s["all"]["fields"]["city"] == [2, 2]          # alias match, and None == None
    assert s["all"]["fields"]["max_exp_years"] == [2, 2]
    assert s["all"]["skills"] == {"extracted": 6, "wrong": 1, "missing": 1}


def test_table_and_write_section(tmp_path, monkeypatch):
    text = run_extract_eval.table(ec.score(SAMPLE, LABELS), len(SAMPLE))
    assert "| seniority | 50% | 100% | 0% |" in text
    assert "| skills precision | 83% | 67% | 100% |" in text        # 5/6, 2/3, 3/3
    assert "| skills recall (owner-noticed misses) | 83% | 67% | 100% |" in text
    results = tmp_path / "results.md"
    results.write_text("# Eval results\n\n<!-- agent-eval:start -->x<!-- agent-eval:end -->\n")
    monkeypatch.setattr(run_extract_eval, "RESULTS", results)
    run_extract_eval.write("first")
    run_extract_eval.write("second")                     # replaces, never duplicates
    out = results.read_text()
    assert out.count(run_extract_eval.START) == 1 and "second" in out and "first" not in out
    assert "agent-eval" in out


def test_ask_field_validates_and_allows_not_stated(monkeypatch):
    answers = iter(["seniorish", "Mid", "?", "", "99", "3"])
    monkeypatch.setattr(builtins, "input", lambda prompt="": next(answers))
    assert label_extract.ask_field("seniority", ec.FIELDS["seniority"]) == "mid"
    assert label_extract.ask_field("work_mode", ec.FIELDS["work_mode"]) is None
    assert label_extract.ask_field("city", None) is None
    assert label_extract.ask_field("min_exp_years", None) == 3       # 99 rejected first


def test_ask_skills_marks_wrong_and_missing(monkeypatch):
    answers = iter(["9", "1, 3", "Django , kafka"])
    monkeypatch.setattr(builtins, "input", lambda prompt="": next(answers))
    wrong, missing = label_extract.ask_skills(["python", "sql", "excel"])
    assert wrong == ["python", "excel"] and missing == ["django", "kafka"]


def test_committed_sample_is_frozen_and_balanced():
    sample = ec.load_sample()
    if not sample:
        pytest.skip("sample not frozen yet")
    groups = [ec.source_group(r["source"]) for r in sample]
    assert groups.count("rules only") == groups.count("rules + LLM") == ec.PER_SOURCE
    assert len({r["job_id"] for r in sample}) == len(sample)
    assert all(set(r["pred"]) == set(ec.FIELDS) | {"skills"} for r in sample)
