"""Fill jobs' structured fields: rules for every job, an LLM only where the rules fall short.

Resumable: it works through rows with extraction_status = 'pending' and commits as it goes,
so a daily quota or a crash just leaves the rest for the next run.

Usage:
  python -m worker.extract --backend rules                  # free pass over all pending jobs
  python -m worker.extract --backend groq --model openai/gpt-oss-20b --limit 200
  python -m worker.extract --backend ollama --model qwen2.5:3b --shard 0/4
"""

import argparse
import json
import logging
import os
import re
import time

from pydantic import ValidationError

from worker.db import connect
from worker.llm import DailyLimitReached, GroqBackend, OllamaBackend
from worker.rules import SENIORITIES, Extraction, needs_llm, rule_extract

log = logging.getLogger("extract")

SYSTEM = (
    "You extract structured fields from a job posting for a job search index. "
    "Use only facts stated in the posting. If a field is not stated, return null "
    "(or an empty list for skills). skills: up to 12 concrete technical or domain skills, "
    "lowercase, most important first. Experience is in whole years. seniority: intern, "
    "fresher (0-1 years), junior (1-2), mid (3-5) or senior (6+ or lead/manager). "
    "Salaries are yearly INR only; leave them null for other currencies."
)


def _nullable(schema: dict) -> dict:
    return {"anyOf": [schema, {"type": "null"}]}


SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["skills", "min_exp_years", "max_exp_years", "seniority", "employment_type",
                 "work_mode", "salary_min_inr", "salary_max_inr"],
    "properties": {
        "skills": {"type": "array", "items": {"type": "string"}},
        "min_exp_years": _nullable({"type": "integer"}),
        "max_exp_years": _nullable({"type": "integer"}),
        "seniority": _nullable({"type": "string", "enum": list(SENIORITIES)}),
        "employment_type": _nullable({"type": "string", "enum": [
            "full_time", "part_time", "intern", "contract", "temporary"]}),
        "work_mode": _nullable({"type": "string", "enum": ["onsite", "hybrid", "remote"]}),
        "salary_min_inr": _nullable({"type": "integer"}),
        "salary_max_inr": _nullable({"type": "integer"}),
    },
}

_RELEVANT = re.compile(r"experience|years|require|qualif|you have|you will|skills|must|"
                       r"proficien|knowledge of|familiar|salary|ctc|lpa|compensation|stack",
                       re.IGNORECASE)


def snippet(title: str, location: str | None, text: str, budget: int = 1500) -> str:
    """Title + the opening + the sentences most likely to hold requirements, within budget."""
    head = text[:500]
    rest = [s for s in re.split(r"(?<=[.!?\n])\s+", text[500:]) if _RELEVANT.search(s)]
    body = head
    for s in rest:
        if len(body) + len(s) > budget:
            break
        body += "\n" + s
    return f"Title: {title}\nLocation: {location or 'unknown'}\n\n{body}"


def merge(rules: Extraction, llm: dict) -> Extraction:
    """Rules win where they found something; the LLM fills the gaps."""
    out = rules.model_dump()
    for k in ("min_exp_years", "max_exp_years", "seniority", "employment_type", "work_mode",
              "salary_min_inr", "salary_max_inr"):
        if out[k] is None and llm.get(k) is not None:
            out[k] = llm[k]
    if len(out["skills"]) < 3:
        extra = [s.strip().lower() for s in llm.get("skills") or [] if s and s.strip()]
        out["skills"] = list(dict.fromkeys(out["skills"] + extra))[:12]
    return Extraction.model_validate(out)


SAVE = """
update jobs set skills = %(skills)s, min_exp_years = %(min_exp_years)s,
  max_exp_years = %(max_exp_years)s, seniority = %(seniority)s,
  employment_type = coalesce(employment_type, %(employment_type)s),
  work_mode = coalesce(work_mode, %(work_mode)s), city = coalesce(city, %(city)s),
  salary_min_inr = %(salary_min_inr)s, salary_max_inr = %(salary_max_inr)s,
  extraction_status = %(status)s, extraction_source = %(source)s,
  extraction_error = %(error)s
where id = %(id)s
"""


def make_backend(name: str, model: str | None):
    if name == "groq":
        return GroqBackend(model or os.getenv("EXTRACT_MODEL", "openai/gpt-oss-20b"),
                           rpm=int(os.getenv("GROQ_RPM", 30)),
                           tpm=int(os.getenv("GROQ_TPM", 8000)))
    if name == "ollama":
        return OllamaBackend(model or os.getenv("OLLAMA_MODEL", "qwen2.5:3b"))
    return None


def run(backend_name: str, model: str | None, limit: int | None, shard: tuple[int, int]):
    backend = make_backend(backend_name, model)
    i, n = shard
    stats = {"rules_only": 0, "llm_ok": 0, "llm_failed": 0, "left_pending": 0,
             "prompt_tokens": 0, "completion_tokens": 0}
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """select id, title, description_text, salary_raw, employment_type, work_mode, city,
                      location_raw
               from jobs where extraction_status = 'pending' and is_active and id %% %s = %s
               order by id limit %s""",
            (n, i, limit),
        )
        rows = cur.fetchall()
        started = time.monotonic()
        for k, (jid, title, desc, sal, emp, mode, city, loc) in enumerate(rows, 1):
            desc = desc or ""
            rules = rule_extract(title, desc, salary_raw=sal, employment_type=emp,
                                 work_mode=mode, city=city)
            row = {**rules.model_dump(), "id": jid, "error": None}
            if not needs_llm(rules):
                row |= {"status": "done", "source": "rules"}
                stats["rules_only"] += 1
            elif backend is None:  # rules pass: keep the rules fields, leave it for the LLM
                row |= {"status": "pending", "source": "rules"}
                stats["left_pending"] += 1
            else:
                prompt = snippet(title, loc, desc)
                err = None
                for _attempt in range(2):  # brief: retry once, then mark failed
                    try:
                        out, usage = backend.complete(SYSTEM, prompt, SCHEMA)
                        merged = merge(rules, out)
                    except DailyLimitReached as e:
                        log.warning("stopping: %s", e)
                        conn.commit()
                        return stats | {"stopped": str(e)}
                    except (ValidationError, json.JSONDecodeError, KeyError, ValueError) as e:
                        err = f"{type(e).__name__}: {str(e)[:200]}"
                        continue
                    stats["prompt_tokens"] += usage.get("prompt_tokens", 0)
                    stats["completion_tokens"] += usage.get("completion_tokens", 0)
                    row = {**merged.model_dump(), "id": jid, "error": None, "status": "done",
                           "source": f"rules+llm:{backend.model}"}
                    stats["llm_ok"] += 1
                    break
                else:
                    row |= {"status": "failed", "source": "rules", "error": err}
                    stats["llm_failed"] += 1
            cur.execute(SAVE, row)
            if k % 20 == 0:
                conn.commit()
                log.info("progress %d/%d (%.1fs/job)", k, len(rows),
                         (time.monotonic() - started) / k)
    return stats


def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format='{"level":"%(levelname)s","msg":"%(message)s"}')
    logging.getLogger("httpx").setLevel(logging.WARNING)
    p = argparse.ArgumentParser()
    p.add_argument("--backend", choices=["rules", "groq", "ollama"], default="rules")
    p.add_argument("--model")
    p.add_argument("--limit", type=int)
    p.add_argument("--shard", default="0/1", help="i/n: only rows with id %% n = i")
    a = p.parse_args()
    i, n = (int(x) for x in a.shard.split("/"))
    log.info(json.dumps(run(a.backend, a.model, a.limit, (i, n))))


if __name__ == "__main__":
    main()
