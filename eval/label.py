"""Label the pooled search results by hand: 2 = great, 1 = ok, 0 = no.

  python -m eval.label --build-pool      # once: run all 5 variants on the snapshot, pool top 20
  python -m eval.label                   # label everything not yet labelled (resumes)
  python -m eval.label --query q07       # just one query
  python -m eval.label --stats           # progress and grade counts

Jobs are shown shuffled, with no hint of which variant or rank produced them. Every answer
is appended to eval/labels.jsonl at once, so you can quit any time and carry on later.
Needs DATABASE_URL pointing at the database that holds the `eval` snapshot.
"""

import argparse
import json
import re
import sys
import time
from collections import Counter

from eval.common import (
    LABELS,
    POOL,
    POOL_DEPTH,
    VARIANTS,
    eval_pool,
    load_jsonl,
    load_labels,
    load_models,
    load_queries,
    pooled,
    run_variant,
)

GUIDE = """How to grade (think: "would this student want to see this job for this search?")
  2  great  - what they asked for: right kind of role, and fits the level/place filters
  1  ok     - related and worth a look, but off in one way (level, stack, or place)
  0  no     - a different kind of job, or clearly wrong for the filters
Keys: 2 / 1 / 0, s = skip for now, b = go back one, q = save and quit
"""

DETAILS = """
select j.id, j.title, c.name, j.city, j.work_mode, j.remote, j.seniority, j.min_exp_years,
       j.max_exp_years, j.skills, j.description_text
from eval.jobs j join eval.companies c on c.id = j.company_id where j.id = any(%s)"""

SHOW_CHARS = 900

# Headings that start the part about the job itself. Most descriptions open with a company
# blurb ("About Plane", "About us"), which tells the labeller nothing about level or stack.
# The list comes from the most common short heading lines in the eval snapshot.
_ROLE = (r"about (?:the|this) (?:role|position|job|opportunity)|(?:the |your )?role(?: overview)?"
         r"|the opportunity|job (?:summary|description)|summary|in this role"
         r"|what you(?:'|’)ll (?:do|be doing)|what you will (?:do|be doing)"
         r"|(?:key )?responsibilities|(?:minimum |basic |required )?(?:requirements|qualifications)"
         r"|who you are|about you|what (?:we(?:'|’)re|we are|we) look(?:ing)? for"
         r"|what you(?:'|’)ll bring|what you bring|what you will need|the impact you will have")
ROLE_HEADING = re.compile(rf"^[ \t#*•-]*(?:{_ROLE})\b[^\n]{{0,45}}$", re.I | re.M)
EXPERIENCE = re.compile(
    r"[^.\n]*\b\d+\s*\+?\s*(?:(?:-|–|to)\s*\d+\s*\+?\s*)?(?:years?|yrs)\b[^.\n]*", re.I)


def role_text(desc: str | None, n: int = SHOW_CHARS) -> str:
    """About n characters starting at the first role heading, or from the top if none."""
    desc = desc or ""
    m = ROLE_HEADING.search(desc)
    return " ".join(desc[m.start() if m else 0:].split())[:n]


def experience_lines(desc: str | None, limit: int = 3) -> list[str]:
    """Sentences anywhere in the description that state years of experience."""
    out: list[str] = []
    for m in EXPERIENCE.finditer(desc or ""):
        s = " ".join(m.group().split())
        if s not in out:
            out.append(s[:200])
        if len(out) == limit:
            break
    return out


def build_pool(depth: int) -> None:
    queries = load_queries()
    embedder, reranker = load_models()
    pool = eval_pool()
    started = time.monotonic()
    with POOL.open("w", encoding="utf-8") as out:
        for n, q in enumerate(queries, 1):
            runs = [run_variant(pool, embedder, reranker, q, flags) for flags in
                    VARIANTS.values()]
            ids = pooled(runs, q["id"], depth)
            out.write(json.dumps({"qid": q["id"], "job_ids": ids}) + "\n")
            print(f"{q['id']} {len(ids):3} jobs to label  ({n}/{len(queries)}, "
                  f"{time.monotonic() - started:.0f}s)")
    pool.close()
    total = sum(len(r["job_ids"]) for r in load_jsonl(POOL))
    print(f"\nPool written to {POOL.name}: {total} (query, job) pairs to label.")


def stats() -> None:
    pools = {r["qid"]: r["job_ids"] for r in load_jsonl(POOL)}
    labels = load_labels()
    grades: Counter = Counter()
    done_total = pool_total = 0
    for qid, ids in pools.items():
        got = labels.get(qid, {})
        done = sum(d in got for d in ids)
        grades.update(got[d] for d in ids if d in got)
        done_total += done
        pool_total += len(ids)
        print(f"{qid}: {done:3}/{len(ids):3}" + ("  done" if done == len(ids) else ""))
    print(f"\nLabelled {done_total}/{pool_total} pairs. Grades: 2 = {grades[2]}, "
          f"1 = {grades[1]}, 0 = {grades[0]}.")


def show(q: dict, row: tuple, i: int, n: int) -> None:
    jid, title, company, city, mode, remote, sen, lo, hi, skills, desc = row
    place = " / ".join(x for x in (city, mode, "remote" if remote else None) if x) or "-"
    exp = "-" if lo is None else (f"{lo}-{hi} yrs" if hi is not None else f"{lo}+ yrs")
    filters = ", ".join(f"{k}={q[k]}" for k in ("level", "city", "remote") if q.get(k))
    print("\n" + "=" * 78)
    print(f"[{q['id']}  {i}/{n}]  Search: \"{q['q']}\"" + (f"   ({filters})" if filters else ""))
    print(f"Wants: {q.get('intent', '')}")
    print("-" * 78)
    print(f"{title}  @ {company}")
    print(f"Place: {place}   Level: {sen or '-'}   Experience: {exp}")
    print(f"Skills: {', '.join(skills or []) or '-'}")
    years = experience_lines(desc)
    for line in years:
        print(f"Says: {line}")
    if not years:
        print("Says: no years of experience anywhere in the description, so Level and "
              "Experience above are the extractor's guess")
    print(role_text(desc))


def ask() -> str:
    while True:
        a = input("grade [2/1/0, s, b, q]: ").strip().lower()
        if a in {"2", "1", "0", "s", "b", "q"}:
            return a
        print("Type 2, 1 or 0 (or s / b / q).")


def label(only: str | None) -> None:
    pools = {r["qid"]: r["job_ids"] for r in load_jsonl(POOL)}
    if not pools:
        raise SystemExit("No pool yet. Run: python -m eval.label --build-pool")
    queries = [q for q in load_queries() if q["id"] in pools and (not only or q["id"] == only)]
    labels = load_labels()
    print(GUIDE)
    db = eval_pool()
    with LABELS.open("a", encoding="utf-8") as out:
        for q in queries:
            ids = pools[q["id"]]
            todo = [d for d in ids if d not in labels.get(q["id"], {})]
            if not todo:
                continue
            with db.connection() as conn, conn.cursor() as cur:
                cur.execute(DETAILS, (todo,))
                rows = {r[0]: r for r in cur.fetchall()}
            k, history = 0, []
            while k < len(todo):
                d = todo[k]
                if d not in rows:  # not in the snapshot (should not happen); skip it
                    k += 1
                    continue
                show(q, rows[d], ids.index(d) + 1, len(ids))
                a = ask()
                if a == "q":
                    print("Saved. Run the same command to carry on.")
                    return
                if a == "b":
                    if history:
                        k = history.pop()
                    continue
                if a != "s":
                    out.write(json.dumps({"qid": q["id"], "job_id": d, "grade": int(a)}) + "\n")
                    out.flush()
                    labels.setdefault(q["id"], {})[d] = int(a)
                history.append(k)
                k += 1
    db.close()
    print("\nNothing left to label. Next: python -m eval.run_search_eval")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser()
    p.add_argument("--build-pool", action="store_true")
    p.add_argument("--depth", type=int, default=POOL_DEPTH,
                   help="top N of each variant to pool (brief: 20)")
    p.add_argument("--stats", action="store_true")
    p.add_argument("--query")
    a = p.parse_args()
    if a.build_pool:
        if POOL.exists() and load_labels():
            raise SystemExit("Labels already exist for this pool; rebuilding it would orphan "
                             "them. Move eval/labels.jsonl away first if you really mean it.")
        build_pool(a.depth)
    elif a.stats:
        stats()
    else:
        label(a.query)


if __name__ == "__main__":
    main()
