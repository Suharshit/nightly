"""Personalised score, company diversity and data-built reasons.

score = 1.0 * rerank_norm
      + 0.3 * cos(job.embedding, profile.taste_embedding)   # liked-jobs centroid
      + 0.2 * skill_overlap(job.skills, resume_skills)      # Jaccard
      + 0.1 * freshness                                     # exp(-days_since_posted / 14)
      - 0.5 * disliked_pattern_penalty

Weights are the brief's starting point; tune them once against the labelled queries, never
per query. The penalty is 1 when the job's company was disliked recently, or the job matches
something the user said to avoid (a "too senior" seniority, a "wrong location" city).
"""

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime

W_RERANK, W_TASTE, W_SKILLS, W_FRESH, W_PENALTY = 1.0, 0.3, 0.2, 0.1, 0.5
FRESH_DAYS = 14
PER_COMPANY_IN_5 = 2


@dataclass
class Profile:
    user_id: str
    taste: str | None = None             # pgvector literal of the liked-jobs centroid
    resume_vec: str | None = None
    resume_skills: list[str] = field(default_factory=list)
    prefs: dict = field(default_factory=dict)
    disliked_companies: set[int] = field(default_factory=set)
    exclude_ids: list[int] = field(default_factory=list)  # disliked, or shown 3+ times

    @property
    def avoid(self) -> dict:
        return self.prefs.get("avoid") or {}


def jaccard(a: list[str], b: list[str]) -> float:
    sa, sb = {x.lower() for x in a}, {x.lower() for x in b}
    return len(sa & sb) / len(sa | sb) if sa and sb else 0.0


def freshness(seen_at: datetime | None, now: datetime) -> float:
    if seen_at is None:
        return 0.0
    days = max(0.0, (now - seen_at).total_seconds() / 86400)
    return math.exp(-days / FRESH_DAYS)


def penalty(job: dict, p: Profile) -> float:
    avoid = p.avoid
    if job.get("company_id") in p.disliked_companies:
        return 1.0
    if job.get("company_id") in set(avoid.get("companies") or []):
        return 1.0
    if job.get("seniority") and job["seniority"] in set(avoid.get("seniority") or []):
        return 1.0
    if job.get("city") and job["city"] in set(avoid.get("cities") or []):
        return 1.0
    return 0.0


def score(job: dict, p: Profile | None, now: datetime, rerank_norm: float,
          use_fresh: bool = True) -> dict:
    """Adds the parts and the final score. Without a profile only rerank + freshness count."""
    parts = {
        "taste": (job.get("taste_sim") or 0.0) if p else 0.0,
        "skills": jaccard(job.get("skills") or [], p.resume_skills) if p else 0.0,
        "fresh": freshness(job.get("seen_at"), now) if use_fresh else 0.0,
        "penalty": penalty(job, p) if p else 0.0,
    }
    final = (W_RERANK * rerank_norm + W_TASTE * parts["taste"] + W_SKILLS * parts["skills"]
             + W_FRESH * parts["fresh"] - W_PENALTY * parts["penalty"])
    return job | {"final_score": round(final, 5), "parts": {k: round(v, 4)
                                                             for k, v in parts.items()}}


def diversify(jobs: list[dict], per_window: int = PER_COMPANY_IN_5, window: int = 5) -> list[dict]:
    """At most `per_window` jobs from one company in any `window` consecutive results.
    Greedy: take the best job that fits; if none fits, take the best remaining anyway."""
    left, out = list(jobs), []
    while left:
        recent = [j.get("company") for j in out[-(window - 1):]]
        pick = next((j for j in left if recent.count(j.get("company")) < per_window), left[0])
        out.append(pick)
        left.remove(pick)
    return out


def _days_ago(seen_at: datetime, now: datetime) -> str:
    days = int((now - seen_at).total_seconds() // 86400)
    return "Posted today" if days <= 0 else ("Posted yesterday" if days == 1
                                             else f"Posted {days} days ago")


def reason(job: dict, p: Profile | None, now: datetime) -> str:
    """'Matches your Python + SQL · Remote · Fresher-friendly · Posted 2 days ago', built only
    from fields we hold, so it is always true."""
    bits = []
    if p and p.resume_skills:
        mine = {s.lower() for s in p.resume_skills}
        matched = [s for s in job.get("skills") or [] if s.lower() in mine][:2]
        if matched:
            bits.append("Matches your " + " + ".join(_label(s) for s in matched))
    cities = set((p.prefs.get("cities") if p else None) or [])
    if job.get("work_mode") == "remote" or job.get("remote"):
        bits.append("Remote")
    elif job.get("city"):
        bits.append(f"In {job['city']}" if job["city"] in cities else job["city"])
    if job.get("seniority") == "intern":
        bits.append("Internship")
    elif job.get("seniority") == "fresher" or (job.get("min_exp_years") or 0) == 0 and \
            job.get("min_exp_years") is not None:
        bits.append("Fresher-friendly")
    elif job.get("min_exp_years") is not None:
        bits.append(f"{job['min_exp_years']}+ yrs")
    if job.get("posted_at"):
        bits.append(_days_ago(job["posted_at"], now))
    return " · ".join(bits)


_LABELS = {"sql": "SQL", "aws": "AWS", "gcp": "GCP", "llm": "LLMs", "ci/cd": "CI/CD",
           "c++": "C++", "rest api": "REST APIs", "ios": "iOS", "postgresql": "PostgreSQL",
           "typescript": "TypeScript", "javascript": "JavaScript", "mongodb": "MongoDB",
           "graphql": "GraphQL", "fastapi": "FastAPI", "node.js": "Node.js", "nlp": "NLP",
           "machine learning": "ML", "github actions": "GitHub Actions", "html": "HTML",
           "css": "CSS", "mysql": "MySQL", "devops": "DevOps", "ui/ux": "UI/UX"}


def _label(skill: str) -> str:
    return _LABELS.get(skill.lower(), skill[:1].upper() + skill[1:])


def personalise(jobs: list[dict], p: Profile | None, now: datetime | None = None,
                *, use_profile: bool = True, use_fresh: bool = True,
                use_diversity: bool = True) -> list[dict]:
    """Score, sort, diversify and attach reasons. use_profile=False is the eval's baseline.
    Searches with a query turn freshness and diversity off: on the labelled queries they cost
    0.078 NDCG@10 for 0.011 recall (eval/results.md). The query-less feed keeps both."""
    now = now or datetime.now(UTC)
    prof = p if use_profile else None
    n = max(len(jobs), 1)
    # With rerank off, the fused order stands in for rerank_norm (1.0 for the top, down to ~0).
    scored = sorted((score(j, prof, now, j["rerank_score"] if j.get("rerank_score") is not None
                           else 1 - i / n, use_fresh) for i, j in enumerate(jobs)),
                    key=lambda j: -j["final_score"])
    ordered = diversify(scored) if use_diversity else scored
    return [j | {"reason": reason(j, p, now)} for j in ordered]
