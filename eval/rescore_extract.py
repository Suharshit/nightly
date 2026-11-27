"""Re-score the extraction sample with the evidence check (worker.extract.merge), no LLM calls.

The frozen sample holds what the LLM produced for the 30 rules + LLM jobs: wherever the rules
left a field empty, the frozen value is the LLM's. So running today's rules on the job text and
merging the frozen values through `merge` gives exactly what the new extractor would store.
Only experience years and seniority change; every other field is scored as frozen.

Usage: python -m eval.rescore_extract     (reads job text from the eval snapshot: DATABASE_URL)
"""

import sys

from eval.extract_common import ROOT, load_labels, load_sample, score, source_group
from eval.run_extract_eval import pct
from worker.db import connect
from worker.extract import merge
from worker.rules import rule_extract

RESULTS = ROOT / "results.md"
START, END = "<!-- extract-rescore:start -->", "<!-- extract-rescore:end -->"
CHANGED = ("seniority", "min_exp_years", "max_exp_years")


def rescore(sample: list[dict], texts: dict[int, tuple[str, str]]) -> list[dict]:
    out = []
    for row in sample:
        if source_group(row["source"]) == "rules + LLM":
            title, desc = texts[row["job_id"]]
            merged = merge(rule_extract(title, desc), row["pred"], desc).model_dump()
            row = row | {"pred": row["pred"] | {f: merged[f] for f in CHANGED}}
        out.append(row)
    return out


def table(before: dict, after: dict) -> str:
    groups = [g for g in ("all", "rules + LLM") if g in before]
    lines = ["| Field | " + " | ".join(f"{g} before | {g} after" for g in groups) + " |",
             "|---|" + "---|---|" * len(groups)]
    for f in CHANGED:
        cells = []
        for g in groups:
            cells += [pct(*before[g]["fields"][f]), pct(*after[g]["fields"][f])]
        lines.append(f"| {f} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def unknown(sample: list[dict], field: str) -> int:
    return sum(r["pred"][field] is None for r in sample
               if source_group(r["source"]) == "rules + LLM")


def write(section: str) -> None:
    body = f"{START}\n### Extraction with the evidence check\n\n{section}\n{END}"
    text = RESULTS.read_text(encoding="utf-8")
    if START in text and END in text:
        text = text[:text.index(START)] + body + text[text.index(END) + len(END):]
    else:
        end = "<!-- extract-eval:end -->"
        i = text.index(end) + len(end) if end in text else len(text)
        text = text[:i] + "\n\n" + body + text[i:]
    RESULTS.write_text(text, encoding="utf-8", newline="\n")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sample, labels = load_sample(), load_labels()
    ids = [r["job_id"] for r in sample]
    with connect() as conn, conn.cursor() as cur:
        cur.execute("select id, title, coalesce(description_text, '') from eval.jobs "
                    "where id = any(%s)", (ids,))
        texts = {i: (t, d) for i, t, d in cur.fetchall()}
    new = rescore(sample, texts)
    before, after = score(sample, labels), score(new, labels)
    n = sum(source_group(r["source"]) != "rules only" for r in sample)
    section = (table(before, after) + "\n\n"
               f"Same {len(labels)} owner labels; only the {n} rules + LLM jobs change. "
               "LLM years are kept only when the posting states that number, and seniority "
               "comes from the title or the kept years, never the LLM. Left unknown after the "
               f"check (of {n}): seniority {unknown(new, 'seniority')} "
               f"(was {unknown(sample, 'seniority')}), min years "
               f"{unknown(new, 'min_exp_years')} (was {unknown(sample, 'min_exp_years')}).")
    print(section)
    write(section)
    print(f"\nWrote the evidence-check section of {RESULTS.name}.")


if __name__ == "__main__":
    main()
