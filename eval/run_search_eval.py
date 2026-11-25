"""Search eval: run the 5 variants on the frozen snapshot and score them against your labels.

  python -m eval.run_search_eval            # print the table and write it into results.md

Only queries with at least one label count. Unlabelled results count as not relevant; the
"judged@10" column says how much of each top 10 you labelled, so low coverage is visible.
Recall is @30 because 30 is the most any variant returns (the reranker sees the fused top 30).
"""

import json
import statistics
import time
from datetime import UTC, datetime

from eval import metrics
from eval.common import (
    EVAL_LIMIT,
    ROOT,
    VARIANTS,
    eval_pool,
    load_labels,
    load_models,
    load_queries,
    run_variant,
)

RESULTS = ROOT / "results.md"
START, END = "<!-- search-eval:start -->", "<!-- search-eval:end -->"


def evaluate() -> tuple[list[dict], dict]:
    labels = load_labels()
    queries = [q for q in load_queries() if labels.get(q["id"])]
    if not queries:
        raise SystemExit("No labels yet. Run: python -m eval.label")
    embedder, reranker = load_models()
    pool = eval_pool()
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute("select frozen_at, jobs from eval.meta")
        frozen_at, jobs = cur.fetchone()
    rows = []
    for name, flags in VARIANTS.items():
        per = {"ndcg@10": [], f"recall@{EVAL_LIMIT}": [], "mrr": [], "judged@10": []}
        ms = []
        for q in queries:
            lab = labels[q["id"]]
            t = time.perf_counter()
            ranked = run_variant(pool, embedder, reranker, q, flags)
            ms.append((time.perf_counter() - t) * 1000)
            per["ndcg@10"].append(metrics.ndcg_at(ranked, lab, 10))
            per[f"recall@{EVAL_LIMIT}"].append(metrics.recall_at(ranked, lab, EVAL_LIMIT))
            per["mrr"].append(metrics.mrr(ranked, lab, EVAL_LIMIT))
            per["judged@10"].append(metrics.judged_at(ranked, lab, 10))
        rows.append({"variant": name, **{k: statistics.fmean(v) for k, v in per.items()},
                     "p50_ms": statistics.median(ms)})
    pool.close()
    n_labels = sum(len(labels[q["id"]]) for q in queries)
    meta = {"queries": len(queries), "labels": n_labels, "jobs": jobs,
            "frozen_at": frozen_at.isoformat(timespec="minutes"),
            "run_at": datetime.now(UTC).isoformat(timespec="minutes")}
    return rows, meta


def table(rows: list[dict], meta: dict) -> str:
    cols = ["ndcg@10", f"recall@{EVAL_LIMIT}", "mrr", "judged@10"]
    lines = [f"Snapshot frozen {meta['frozen_at']} ({meta['jobs']} active jobs). "
             f"{meta['queries']} queries, {meta['labels']} hand labels. Run {meta['run_at']} "
             f"by `python -m eval.run_search_eval`.", "",
             "| Variant | NDCG@10 | Recall@30 | MRR | judged@10 | p50 ms |",
             "| --- | --- | --- | --- | --- | --- |"]
    for r in rows:
        lines.append(f"| {r['variant']} | " + " | ".join(f"{r[c]:.3f}" for c in cols)
                     + f" | {r['p50_ms']:.0f} |")
    return "\n".join(lines)


def write(section: str) -> None:
    body = f"{START}\n## Search\n\n{section}\n{END}"
    text = RESULTS.read_text(encoding="utf-8") if RESULTS.exists() else "# Eval results\n\n"
    if START in text and END in text:
        text = text[:text.index(START)] + body + text[text.index(END) + len(END):]
    else:
        text = text.rstrip() + "\n\n" + body + "\n"
    RESULTS.write_text(text, encoding="utf-8", newline="\n")


def main() -> None:
    rows, meta = evaluate()
    section = table(rows, meta)
    print(section)
    write(section)
    print(f"\nWritten to {RESULTS.relative_to(ROOT.parent)}")
    print(json.dumps(meta))


if __name__ == "__main__":
    main()
