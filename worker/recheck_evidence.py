"""Apply the evidence check (worker.extract.merge) to jobs already extracted with an LLM.

No LLM calls: where today's rules leave a field empty, the stored value is the LLM's, so
re-merging the stored values gives what the new extractor would have saved. Only
min_exp_years, max_exp_years and seniority can change.

Usage:
  python -m worker.recheck_evidence                 # dry run on public.jobs: counts only
  python -m worker.recheck_evidence --schema eval_x # another schema (e.g. a copy for the eval)
  python -m worker.recheck_evidence --write         # save the changes
"""

import argparse
import collections
import json

from worker.db import connect
from worker.extract import merge
from worker.rules import rule_extract

FIELDS = ("min_exp_years", "max_exp_years", "seniority")


def changes(rows) -> list[tuple[int, dict, dict]]:
    out = []
    for jid, title, desc, *stored in rows:
        old = dict(zip(FIELDS, stored, strict=True))
        new = merge(rule_extract(title, desc or ""), old, desc or "").model_dump()
        new = {f: new[f] for f in FIELDS}
        if new != old:
            out.append((jid, old, new))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--schema", default="public")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    if not args.schema.replace("_", "").isalnum():
        raise SystemExit("schema must be a plain name")
    with connect() as conn, conn.cursor() as cur:
        cur.execute(f"""select id, title, description_text, {", ".join(FIELDS)}
                        from {args.schema}.jobs
                        where extraction_status = 'done' and extraction_source like '%%llm%%'""")
        rows = cur.fetchall()
        diff = changes(rows)
        moves = collections.Counter(f"{o['seniority']}->{n['seniority']}" for _, o, n in diff
                                    if o["seniority"] != n["seniority"])
        years = sum(o["min_exp_years"] != n["min_exp_years"] for _, o, n in diff)
        print(json.dumps({"schema": args.schema, "llm_jobs": len(rows), "changed": len(diff),
                          "min_years_changed": years, "seniority_moves": moves.most_common()}))
        if args.write:
            for jid, _, n in diff:
                cur.execute(f"""update {args.schema}.jobs set min_exp_years = %s,
                                max_exp_years = %s, seniority = %s where id = %s""",
                            (n["min_exp_years"], n["max_exp_years"], n["seniority"], jid))
            conn.commit()
            print(f"saved {len(diff)} jobs")


if __name__ == "__main__":
    main()
