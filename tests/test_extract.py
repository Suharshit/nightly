from worker.extract import SCHEMA, merge, snippet
from worker.llm import RateLimiter, _seconds
from worker.rules import Extraction


def test_merge_rules_win_llm_fills_gaps():
    rules = Extraction(skills=["python"], min_exp_years=None, seniority="mid")
    llm = {"skills": ["Python", "Kafka", " SQL "], "min_exp_years": 3, "max_exp_years": 5,
           "seniority": "senior", "employment_type": None, "work_mode": "remote",
           "salary_min_inr": None, "salary_max_inr": None}
    out = merge(rules, llm)
    assert out.seniority == "mid"  # rules win
    assert out.min_exp_years == 3 and out.max_exp_years == 5 and out.work_mode == "remote"
    assert out.skills == ["python", "kafka", "sql"]  # deduped, lowercased


def test_merge_rejects_bad_llm_values():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        merge(Extraction(), {"min_exp_years": -3})


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
