"""Extraction eval: the frozen sample, the owner's labels, and per-field scoring.

The sample is 30 jobs extracted by rules alone and 30 where an LLM filled the gaps, drawn
with a fixed seed from the frozen `eval` snapshot. Each sample row records what the
extractor produced at freeze time, so later re-extraction never changes what is scored.

Labels are the owner's. Single-value fields are labelled blind (the extracted value is not
shown). Skills are judged instead: the owner marks wrong ones and adds missing ones, which
gives precision exactly and recall as far as the owner noticed omissions.
"""

import json
from pathlib import Path

from worker.rules import SENIORITIES
from worker.text import find_city

ROOT = Path(__file__).parent
SAMPLE = ROOT / "extract_sample.jsonl"
LABELS = ROOT / "extract_labels.jsonl"
PER_SOURCE = 30
SEED = 20261127

# Single-value fields: (name, allowed values or None for free text / numbers).
FIELDS: dict[str, tuple[str, ...] | None] = {
    "seniority": SENIORITIES,
    "min_exp_years": None,
    "max_exp_years": None,
    "work_mode": ("onsite", "hybrid", "remote"),
    "city": None,
    "employment_type": ("full_time", "part_time", "intern", "contract", "temporary"),
}
NUMERIC = {"min_exp_years", "max_exp_years"}


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def load_sample() -> list[dict]:
    return load_jsonl(SAMPLE)


def load_labels() -> dict[int, dict]:
    """{job_id: label}; a later line for the same job overrides an earlier one."""
    return {row["job_id"]: row for row in load_jsonl(LABELS)}


def source_group(source: str | None) -> str:
    return "rules + LLM" if source and "llm" in source else "rules only"


def norm(field: str, value):
    """Comparable form of a value: None for "not stated", canonical city names, ints."""
    if value is None or value == "":
        return None
    if field == "city":
        return find_city(str(value)) or str(value).strip().title()
    if field in NUMERIC:
        return int(value)
    return str(value).strip().lower()


def score(sample: list[dict], labels: dict[int, dict]) -> dict:
    """Per group ("all", "rules only", "rules + LLM"): field -> (correct, labelled), plus
    skill counts for precision and recall."""
    out: dict[str, dict] = {}
    for row in sample:
        lab = labels.get(row["job_id"])
        if not lab:
            continue
        for group in ("all", source_group(row["source"])):
            g = out.setdefault(group, {"jobs": 0, "fields": {f: [0, 0] for f in FIELDS},
                                       "skills": {"extracted": 0, "wrong": 0, "missing": 0}})
            g["jobs"] += 1
            for f in FIELDS:
                if f in lab["fields"]:
                    g["fields"][f][1] += 1
                    g["fields"][f][0] += norm(f, row["pred"][f]) == norm(f, lab["fields"][f])
            g["skills"]["extracted"] += len(row["pred"]["skills"])
            g["skills"]["wrong"] += len(lab["skills_wrong"])
            g["skills"]["missing"] += len(lab["skills_missing"])
    return out
