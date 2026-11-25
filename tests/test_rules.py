from worker.rules import (
    experience,
    find_skills,
    needs_llm,
    rule_extract,
    salary_inr,
    title_seniority,
)


def test_title_seniority():
    assert title_seniority("Software Engineering Intern") == "intern"
    assert title_seniority("Senior Backend Engineer") == "senior"
    assert title_seniority("Sr. Data Analyst") == "senior"
    assert title_seniority("Graduate Engineer Trainee") == "intern"
    assert title_seniority("Software Engineer I") == "junior"
    assert title_seniority("SDE 1, Payments") == "junior"
    assert title_seniority("Software Engineer II") == "mid"
    assert title_seniority("Product Management - Paytm Insurance I Exp - 6 to 8") is None
    assert title_seniority("Backend Engineer") is None


def test_experience():
    assert experience("You have 2-4 years of experience with Python.") == (2, 4)
    assert experience("Minimum 5+ years experience in sales.") == (5, None)
    assert experience("We welcome freshers and final-year students.") == (0, 1)
    assert experience("Founded 10 years ago. Great team.") == (None, None)


def test_skills_rank_and_go():
    s = find_skills("Backend Engineer (Go)", "We use Go, Kafka and PostgreSQL. Kafka at scale.")
    assert s[0] == "go" and "kafka" in s and "postgresql" in s
    assert "go" not in find_skills("Sales Lead", "Ready to go the extra mile? Let's go.")
    assert "security" not in find_skills("Engineer", "We may ask for your social security number.")


def test_salary():
    assert salary_inr("CTC 12-18 LPA") == (1_200_000, 1_800_000)
    assert salary_inr("₹8L – ₹12L") == (800_000, 1_200_000)
    assert salary_inr("$160K – $225K") == (None, None)


def test_rule_extract_and_needs_llm():
    x = rule_extract("Product Manager - Insurance I Exp - 6 to 8",
                     "Requires 6-8 years of experience in product management and SQL.")
    assert x.seniority == "senior" and (x.min_exp_years, x.max_exp_years) == (6, 8)
    assert x.employment_type == "full_time"
    y = rule_extract("Product Research Specialist", "Join us.")
    assert needs_llm(y)
