from worker.extract import SCHEMA, merge, snippet
from worker.llm import RateLimiter, _seconds
from worker.rules import Extraction, stated_years


def test_merge_rules_win_llm_fills_gaps():
    rules = Extraction(skills=["python"], min_exp_years=None, seniority="mid")
    llm = {"skills": ["Python", "Kafka", " SQL "], "min_exp_years": 3, "max_exp_years": 5,
           "seniority": "senior", "employment_type": None, "work_mode": "remote",
           "salary_min_inr": None, "salary_max_inr": None}
    out = merge(rules, llm, "You bring 3-5 years of backend experience.")
    assert out.seniority == "mid"  # rules win
    assert out.min_exp_years == 3 and out.max_exp_years == 5 and out.work_mode == "remote"
    assert out.skills == ["python", "kafka", "sql"]  # deduped, lowercased


def test_merge_keeps_llm_years_only_when_the_posting_states_them():
    llm = {"min_exp_years": 2, "max_exp_years": 4, "seniority": "senior"}
    out = merge(Extraction(), llm, "Strong Go skills. Great team.")
    assert out.min_exp_years is None and out.max_exp_years is None
    assert out.seniority is None            # the LLM's seniority guess is never used
    out = merge(Extraction(), llm, "Ideally two years with Go, up to 4 yrs is fine.")
    assert (out.min_exp_years, out.max_exp_years) == (2, 4)
    assert out.seniority == "junior"         # derived from the kept years
    assert merge(Extraction(), {"min_exp_years": -3}).min_exp_years is None


def test_stated_years_finds_numbers_and_fresher_wording():
    assert stated_years("3+ years in Java; 2-4 yrs of SQL; five years total") == {2, 3, 4, 5}
    assert stated_years("Freshers welcome") == {0, 1}
    assert stated_years("Founded in 2019, 500 people, someone years") == set()


def test_schema_is_strict_compatible():
    # Groq strict mode: every property required, no extra properties.
    assert SCHEMA["additionalProperties"] is False
    assert set(SCHEMA["required"]) == set(SCHEMA["properties"])


def test_snippet_keeps_requirements_within_budget():
    text = "About us. " * 80 + "You have 3+ years of experience with Go. " + "Perks. " * 50
    s = snippet("Backend Engineer", "Bengaluru", text, budget=1500)
    assert "3+ years" in s and len(s) < 1600


def test_groq_time_parsing():
    assert _seconds("7.66s") == 7.66
    assert abs(_seconds("2m59.56s") - 179.56) < 1e-6
    assert _seconds("12") == 12


def test_rate_limiter_allows_within_budget():
    rl = RateLimiter(rpm=2, tpm=1000)
    rl.wait(400)
    rl.wait(400)  # both fit in the first minute without sleeping
    assert len(rl.calls) == 2


def test_recheck_lists_only_jobs_whose_values_change():
    from worker.recheck_evidence import changes
    rows = [(1, "Backend Engineer", "You have 3+ years of experience.", 3, None, "mid"),
            (2, "Backend Engineer", "Build services.", 4, None, "mid")]
    assert changes(rows) == [(2, {"min_exp_years": 4, "max_exp_years": None, "seniority": "mid"},
                              {"min_exp_years": None, "max_exp_years": None, "seniority": None})]
