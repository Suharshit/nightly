"""Eval plumbing: metrics, pooling, label loading, and the results.md writer."""

import json
import math

import pytest

from eval import common, metrics, run_search_eval

LAB = {1: 2, 2: 0, 3: 1, 4: 2}  # job_id -> grade


def test_ndcg_perfect_and_worst():
    assert metrics.ndcg_at([1, 4, 3, 2], LAB, 10) == pytest.approx(1.0)
    assert metrics.ndcg_at([2, 99], LAB, 10) == 0.0
    assert metrics.ndcg_at([1], {1: 0}, 10) == 0.0  # nothing relevant labelled


def test_ndcg_value():
    got = metrics.ndcg_at([3, 1], LAB, 10)
    dcg = 1 / math.log2(2) + 3 / math.log2(3)
    ideal = 3 + 3 / math.log2(3) + 1 / math.log2(4)
    assert got == pytest.approx(dcg / ideal)


def test_recall_mrr_judged():
    assert metrics.recall_at([1, 2, 99], LAB, 30) == pytest.approx(1 / 3)
    assert metrics.mrr([2, 99, 3], LAB, 30) == pytest.approx(1 / 3)
    assert metrics.mrr([2, 99], LAB, 30) == 0.0
    assert metrics.judged_at([1, 99, 2, 98], LAB, 10) == 0.5


def test_pooled_is_union_shuffled_and_reproducible():
    runs = [[1, 2, 3], [3, 4], [5] + list(range(100, 130))]
    a = common.pooled(runs, "q01", depth=2)
    assert sorted(a) == [1, 2, 3, 4, 5, 100]
    assert a == common.pooled(runs, "q01", depth=2)
    assert a != sorted(a) or common.pooled(runs, "q02", depth=2) != a


def test_variants_add_one_stage_each():
    v = list(common.VARIANTS.values())
    assert v[2] == {"use_rerank": False, "use_final": False}
    assert v[3] == {"use_final": False}
    assert v[4] == {"use_fresh": True, "use_diversity": True}   # the old query behaviour
    assert v[5] == {}                                           # as /matches serves a query


def test_labels_later_line_wins(tmp_path, monkeypatch):
    f = tmp_path / "labels.jsonl"
    f.write_text("\n".join(json.dumps(r) for r in [
        {"qid": "q01", "job_id": 7, "grade": 0}, {"qid": "q01", "job_id": 7, "grade": 2},
        {"qid": "q02", "job_id": 7, "grade": 1}]) + "\n", encoding="utf-8")
    monkeypatch.setattr(common, "LABELS", f)
    assert common.load_labels() == {"q01": {7: 2}, "q02": {7: 1}}


def test_queries_file_is_valid():
    qs = common.load_queries()
    assert len(qs) == 50 and len({q["id"] for q in qs}) == 50
    assert all(q["q"] and q["level"] in (None, "student", "fresher", "junior") for q in qs)
    assert all("grade" not in q and "labels" not in q for q in qs)  # labels live elsewhere


def test_results_writer_replaces_its_section(tmp_path, monkeypatch):
    f = tmp_path / "results.md"
    monkeypatch.setattr(run_search_eval, "RESULTS", f)
    f.write_text("# Eval results\n\nAgent stuff stays.\n", encoding="utf-8")
    run_search_eval.write("first")
    run_search_eval.write("second")
    text = f.read_text(encoding="utf-8")
    assert "Agent stuff stays." in text and "second" in text and "first" not in text
    assert text.count(run_search_eval.START) == 1


class _FakeDB:
    """Stands in for the eval DB pool: returns a job row for every requested id."""

    def __init__(self):
        self.closed = False

    def connection(self):
        return self

    def cursor(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params):
        self.ids = params[0]

    def fetchall(self):
        return [(d, f"Job {d}", "Acme", "Pune", None, False, "junior", 0, 1, ["python"],
                 "Build APIs.") for d in self.ids]

    def close(self):
        self.closed = True


def test_label_loop_writes_back_skips_and_resumes(tmp_path, monkeypatch, capsys):
    from eval import label
    pool_f, labels_f = tmp_path / "pool.jsonl", tmp_path / "labels.jsonl"
    pool_f.write_text(json.dumps({"qid": "q01", "job_ids": [10, 11, 12, 13]}) + "\n",
                      encoding="utf-8")
    for mod in (common, label):
        monkeypatch.setattr(mod, "POOL", pool_f)
        monkeypatch.setattr(mod, "LABELS", labels_f)
    monkeypatch.setattr(label, "eval_pool", _FakeDB)
    keys = iter(["2", "1", "x", "b", "0", "s", "0"])  # x is rejected; b re-grades job 11
    monkeypatch.setattr("builtins.input", lambda _: next(keys))
    label.label("q01")
    assert common.load_labels() == {"q01": {10: 2, 11: 0, 13: 0}}  # 12 was skipped
    assert "Type 2, 1 or 0" in capsys.readouterr().out

    keys2 = iter(["1"])  # a second session only asks about the skipped job
    monkeypatch.setattr("builtins.input", lambda _: next(keys2))
    label.label("q01")
    assert common.load_labels()["q01"] == {10: 2, 11: 0, 12: 1, 13: 0}


PLANE_LIKE = """ABOUT PLANE

Plane's mission is to build the infrastructure the world's work runs on. """ + "Blurb. " * 200 + """

About the role:
Build backend services in Node.js.

Requirements
3+ years of backend experience. Strong SQL.
"""


def test_role_text_skips_the_company_blurb():
    from eval.label import role_text
    text = role_text(PLANE_LIKE)
    assert text.startswith("About the role: Build backend services")
    assert "3+ years of backend experience" in text
    assert len(role_text("x" * 5000)) == 900


def test_role_text_falls_back_to_the_top_and_ignores_about_us():
    from eval.label import role_text
    assert role_text("About us\nWe sell shoes.\nAbout the team\nNice people.") \
        == "About us We sell shoes. About the team Nice people."
    assert role_text(None) == ""
    # A heading word inside a sentence is not a heading.
    assert role_text("We value the role of tests.\nMore.").startswith("We value")


def test_role_heading_variants():
    from eval.label import role_text
    for h in ("What you’ll do", "What You'll Be Doing", "Key Responsibilities:",
              "Minimum Qualifications", "What we're looking for", "## Who you are",
              "Role Overview", "The Opportunity"):
        assert role_text(f"About Acme\nWe are great.\n{h}\nShip code.").startswith(h)


def test_experience_lines_find_years_anywhere():
    from eval.label import experience_lines
    assert experience_lines(PLANE_LIKE) == ["3+ years of backend experience"]
    assert experience_lines("Need 2-4 yrs in Go. Also 5 years Java. Founded in 2019.") == \
        ["Need 2-4 yrs in Go", "Also 5 years Java"]
    assert experience_lines(None) == []


def test_build_pool_refuses_when_labels_exist(tmp_path, monkeypatch):
    from eval import label
    pool_f, labels_f = tmp_path / "pool.jsonl", tmp_path / "labels.jsonl"
    pool_f.write_text("{}\n", encoding="utf-8")
    labels_f.write_text(json.dumps({"qid": "q01", "job_id": 1, "grade": 2}) + "\n",
                        encoding="utf-8")
    for mod in (common, label):
        monkeypatch.setattr(mod, "POOL", pool_f)
        monkeypatch.setattr(mod, "LABELS", labels_f)
    monkeypatch.setattr("sys.argv", ["label", "--build-pool"])
    with pytest.raises(SystemExit, match="orphan"):
        label.main()
