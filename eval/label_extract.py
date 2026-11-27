"""Freeze the extraction sample and label it (the owner labels; never an LLM).

Usage:
  python -m eval.label_extract --sample   # freeze 30 rules-only + 30 rules+LLM jobs (once)
  python -m eval.label_extract            # label the next unlabelled job; q to stop any time
  python -m eval.label_extract --stats    # how many are done

For each job you see the title, location and the role part of the description, and type what
the posting itself says. Type ? (or just Enter) when the posting does not state a field.
Single-value fields are blind: the extractor's answer is not shown. For skills you see the
extracted list and mark the wrong ones, then add important skills it missed.
Answers are appended to eval/extract_labels.jsonl; a later answer for a job replaces it.
"""

import argparse
import json
import random
import sys

from eval.extract_common import (
    FIELDS,
    LABELS,
    NUMERIC,
    PER_SOURCE,
    SAMPLE,
    SEED,
    load_labels,
    load_sample,
    source_group,
)
from eval.label import experience_lines, role_text
from worker.db import connect

PRED_COLS = ("seniority", "min_exp_years", "max_exp_years", "work_mode", "city",
             "employment_type", "skills")


def freeze() -> None:
    if SAMPLE.exists():
        sys.exit(f"{SAMPLE.name} already exists; the sample is frozen.")
    with connect() as conn, conn.cursor() as cur:
        cur.execute(f"""select id, extraction_source, {", ".join(PRED_COLS)} from eval.jobs
                        where extraction_status = 'done' and canonical_id is null
                        order by id""")
        rows = cur.fetchall()
    rng = random.Random(SEED)
    picked = []
    for group in ("rules only", "rules + LLM"):
        pool = [r for r in rows if source_group(r[1]) == group]
        picked += rng.sample(pool, PER_SOURCE)
    rng.shuffle(picked)                 # mix the groups so the labeller cannot tell them apart
    with SAMPLE.open("w", encoding="utf-8") as f:
        for r in picked:
            pred = dict(zip(PRED_COLS, r[2:], strict=True))
            pred["skills"] = list(pred["skills"] or [])
            f.write(json.dumps({"job_id": r[0], "source": r[1], "pred": pred}) + "\n")
    print(f"Froze {len(picked)} jobs into {SAMPLE.name}.")


def stats() -> None:
    sample, labels = load_sample(), load_labels()
    done = sum(r["job_id"] in labels for r in sample)
    print(f"Labelled {done}/{len(sample)} jobs.")


def ask_field(name: str, allowed: tuple[str, ...] | None):
    hint = "/".join(allowed) if allowed else ("a number" if name in NUMERIC else "a city")
    while True:
        a = input(f"  {name} [{hint}, ? = not stated]: ").strip()
        if a.lower() == "q":
            raise KeyboardInterrupt
        if a in ("", "?"):
            return None
        if name in NUMERIC:
            if a.isdigit() and int(a) <= 40:
                return int(a)
        elif allowed is None or a.lower() in allowed:
            return a.lower() if allowed else a
        print(f"    please type {hint}, ? or q")


def ask_skills(extracted: list[str]) -> tuple[list[str], list[str]]:
    for i, s in enumerate(extracted, 1):
        print(f"    {i}. {s}")
    while True:
        a = input("  wrong skills by number (e.g. 2,5; Enter = none): ").strip()
        if a.lower() == "q":
            raise KeyboardInterrupt
        try:
            nums = {int(x) for x in a.replace(" ", "").split(",") if x}
        except ValueError:
            print("    numbers separated by commas")
            continue
        if all(1 <= n <= len(extracted) for n in nums):
            break
        print(f"    numbers between 1 and {len(extracted)}")
    wrong = [extracted[n - 1] for n in sorted(nums)]
    a = input("  important skills it missed (comma-separated; Enter = none): ").strip()
    if a.lower() == "q":
        raise KeyboardInterrupt
    missing = [s.strip().lower() for s in a.split(",") if s.strip()]
    return wrong, missing


def label() -> None:
    sample, labels = load_sample(), load_labels()
    if not sample:
        sys.exit("No sample yet: run with --sample first.")
    todo = [r for r in sample if r["job_id"] not in labels]
    print(f"{len(sample) - len(todo)}/{len(sample)} done. q quits; answers are saved per job.")
    with connect() as conn, conn.cursor() as cur:
        for n, row in enumerate(todo, len(sample) - len(todo) + 1):
            cur.execute("""select j.title, c.name, j.location_raw, j.description_text
                           from eval.jobs j join companies c on c.id = j.company_id
                           where j.id = %s""", (row["job_id"],))
            title, company, location, desc = cur.fetchone()
            print("\n" + "=" * 78)
            print(f"[{n}/{len(sample)}]  {title}  @ {company}")
            print(f"Location as posted: {location or '-'}")
            for line in experience_lines(desc):
                print(f"Says: {line}")
            print("-" * 78)
            print(role_text(desc, 1400))
            print("-" * 78)
            try:
                fields = {f: ask_field(f, allowed) for f, allowed in FIELDS.items()}
                print("  extracted skills:")
                wrong, missing = ask_skills(row["pred"]["skills"])
            except (KeyboardInterrupt, EOFError):   # q, Ctrl+C or end of input
                print("\nStopped; this job was not saved.")
                return
            with LABELS.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"job_id": row["job_id"], "fields": fields,
                                    "skills_wrong": wrong, "skills_missing": missing}) + "\n")
    print("\nAll jobs labelled. Run: python -m eval.run_extract_eval")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sample", action="store_true", help="freeze the sample (once)")
    ap.add_argument("--stats", action="store_true", help="show progress")
    args = ap.parse_args()
    if args.sample:
        freeze()
    elif args.stats:
        stats()
    else:
        label()


if __name__ == "__main__":
    main()
