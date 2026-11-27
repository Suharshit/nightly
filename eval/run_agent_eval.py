"""Run the labelled chat turns through the real agent on each model and score them.

  python -m eval.run_agent_eval                          # both models, all labelled turns
  python -m eval.run_agent_eval --models openai/gpt-oss-120b --case a17
  python -m eval.run_agent_eval --rescore                # re-score the saved runs (no API calls)

Needs DATABASE_URL (the database with the `eval` snapshot) and GROQ_API_KEY. Every turn runs
inside one transaction that is rolled back: a throwaway user, its saved prefs and the earlier
messages of each turn are set up per turn and leave nothing behind. There is no fallback
model here, so each model is measured on its own. A turn hit by a rate limit waits and is
run again. Raw results go to eval/agent_runs.jsonl, the table into eval/results.md.
"""

import argparse
import json
import math
import os
import statistics
import sys
import time
from contextlib import contextmanager
from datetime import UTC, datetime

from eval.agent_common import load_agent_labels, load_cases, score
from eval.common import ROOT, load_jsonl, load_models

MODELS = ["openai/gpt-oss-120b", "qwen/qwen3.8-27b"]
RESUME_SKILLS = ["python", "sql", "django", "git", "rest api"]
RESULTS = ROOT / "results.md"
RUNS = ROOT / "agent_runs.jsonl"
START, END = "<!-- agent-eval:start -->", "<!-- agent-eval:end -->"


class OneConn:
    """The agent's pool, backed by the single connection that holds the transaction."""

    def __init__(self, conn):
        self.conn = conn

    @contextmanager
    def connection(self):
        yield self.conn


def setup_user(cur, embedder) -> dict:
    from api.app.search.pipeline import to_pgvector
    cur.execute("insert into auth.users (id, email) select u, 'agent-eval-' || u || '@test' "
                "from gen_random_uuid() u returning id, email")
    uid, email = cur.fetchone()
    user = {"id": str(uid), "email": email}
    vec = to_pgvector(embedder.query("python backend developer: " + ", ".join(RESUME_SKILLS)))
    cur.execute("insert into profiles (user_id, email, resume_text, resume_embedding, "
                "resume_skills) values (%s, %s, 'eval resume', %s::vector, %s)",
                (user["id"], user["email"], vec, RESUME_SKILLS))
    return user


def prepare(cur, user: dict, case: dict) -> None:
    cur.execute("update profiles set prefs = %s::jsonb where user_id = %s",
                (json.dumps(case.get("prefs") or {}), user["id"]))
    for m in case.get("history") or []:
        extra = {"shown": m["shown"], "job_ids": [int(s.split()[0]) for s in m["shown"]]} \
            if m.get("shown") else None
        cur.execute("insert into messages (user_id, role, content, tool_calls) "
                    "values (%s, %s, %s, %s::jsonb)",
                    (user["id"], m["role"], m["content"], json.dumps(extra) if extra else None))


def run_model(conn, embedder, reranker, model: str, cases: list[dict]) -> list[dict]:
    from api.app import profile as prof
    from api.app.agent import loop
    from api.app.agent.llm import GroqChat

    agent = loop.Agent(OneConn(conn), embedder, reranker, GroqChat(model, fallback=model))
    # Shown-job logging is not measured here, and snapshot jobs may be gone from `jobs`.
    real_log_shown, prof.log_shown = prof.log_shown, lambda *a, **k: None
    out = []
    try:
        with conn.cursor() as cur:
            user = setup_user(cur, embedder)
            for n, case in enumerate(cases, 1):
                turn = run_turn(cur, agent, user, case)
                out.append(record(model, case, turn))
                print(f"{model}  {case['id']} ({n}/{len(cases)}): "
                      f"{[c['name'] for c in turn.tool_calls] or 'no tool'}  "
                      f"{turn.latency_ms} ms" + (f"  [{turn.error[:80]}]" if turn.error else ""))
    finally:
        prof.log_shown = real_log_shown
    return out


def run_turn(cur, agent, user: dict, case: dict):
    import psycopg

    from api.app.agent.loop import Turn
    from api.app.agent.schemas import AgentReply
    for attempt in range(4):
        cur.execute("savepoint turn")
        try:
            prepare(cur, user, case)
            turn = agent.respond(user, case["message"])
        except psycopg.Error as e:      # count it as a failed turn, keep going
            turn = Turn(reply=AgentReply(reply="(database error)"), jobs=[], json_valid=False,
                        model=agent.llm.model, error=f"db: {e}".splitlines()[0][:200])
        cur.execute("rollback to savepoint turn")
        if not (turn.error and "rate limited" in turn.error) or attempt == 3:
            return turn
        print(f"  {case['id']}: rate limited, waiting 30 s")
        time.sleep(30)
    return turn


def record(model: str, case: dict, turn) -> dict:
    return {"id": case["id"], "model": model, "calls": turn.tool_calls,
            "json_valid": turn.json_valid, "dropped": turn.dropped,
            "latency_ms": turn.latency_ms, "usage": turn.usage, "reply": turn.reply.reply,
            "job_ids": turn.reply.job_ids, "error": turn.error}


def pct(values: list[float], q: float) -> float:
    """Nearest-rank percentile."""
    s = sorted(values)
    return s[min(len(s), max(1, math.ceil(q * len(s)))) - 1] if s else 0.0


def summarise(runs: list[dict], labels: dict) -> list[dict]:
    rows = []
    for model in dict.fromkeys(r["model"] for r in runs):
        rs = [r for r in runs if r["model"] == model]
        scored = [score(labels[r["id"]], r["calls"]) for r in rs]
        args = [s["args_ok"] for s in scored if s["args_ok"] is not None]
        lat = [r["latency_ms"] for r in rs]
        rows.append({
            "model": model, "turns": len(rs),
            "tool_acc": sum(s["tool_ok"] for s in scored) / len(rs),
            "arg_acc": sum(args) / len(args) if args else None, "arg_turns": len(args),
            "json_valid": sum(r["json_valid"] for r in rs) / len(rs),
            "hallucinated": sum(bool(r["dropped"]) for r in rs) / len(rs),
            "p50_ms": statistics.median(lat), "p95_ms": pct(lat, 0.95),
            "prompt_tokens": statistics.mean(r["usage"].get("prompt_tokens", 0) for r in rs)})
    return rows


def table(rows: list[dict], when: str) -> str:
    lines = [f"{rows[0]['turns']} hand-labelled chat turns (eval/convos.jsonl, labels in "
             f"eval/agent_labels.jsonl), no fallback model. Run {when} by "
             f"`python -m eval.run_agent_eval`.", "",
             "| Model | Tool accuracy | Argument accuracy | JSON valid | Invented jobs | "
             "p50 ms | p95 ms | Prompt tokens / turn |",
             "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in rows:
        arg = "-" if r["arg_acc"] is None else f"{r['arg_acc']:.0%} ({r['arg_turns']})"
        lines.append(f"| {r['model']} | {r['tool_acc']:.0%} | {arg} | {r['json_valid']:.0%} | "
                     f"{r['hallucinated']:.0%} | {r['p50_ms']:.0f} | {r['p95_ms']:.0f} | "
                     f"{r['prompt_tokens']:.0f} |")
    lines += ["", "Invented jobs = share of turns where the reply named a job no tool returned "
              "(the guardrail removed it before the user saw it). Latency includes waiting for "
              "Groq's free-tier limit of 8K tokens a minute: with no fallback model, a turn that "
              "hits it waits up to 20 s, so p50/p95 measure the free tier more than the model."]
    return "\n".join(lines)


def write(section: str) -> None:
    body = f"{START}\n## Agent\n\n{section}\n{END}"
    text = RESULTS.read_text(encoding="utf-8") if RESULTS.exists() else "# Eval results\n\n"
    if START in text and END in text:
        text = text[:text.index(START)] + body + text[text.index(END) + len(END):]
    else:
        text = text.rstrip() + "\n\n" + body + "\n"
    RESULTS.write_text(text, encoding="utf-8", newline="\n")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser()
    p.add_argument("--models", nargs="+", default=MODELS)
    p.add_argument("--case")
    p.add_argument("--rescore", action="store_true",
                   help="score eval/agent_runs.jsonl against the current labels; no API calls")
    a = p.parse_args()
    labels = load_agent_labels()
    if a.rescore:
        runs = [r for r in load_jsonl(RUNS) if r["id"] in labels]
        when = datetime.fromtimestamp(RUNS.stat().st_mtime, UTC).isoformat(timespec="minutes")
        section = table(summarise(runs, labels), when)
        print(section)
        write(section)
        return
    cases = [c for c in load_cases() if c["id"] in labels and (not a.case or c["id"] == a.case)]
    if not cases:
        raise SystemExit("No labelled turns yet. Run: python -m eval.label_agent")
    import psycopg
    embedder, reranker = load_models()
    conn = psycopg.connect(os.environ["DATABASE_URL"], autocommit=False)
    try:
        conn.execute("set search_path = eval, public")
        runs = [r for m in a.models for r in run_model(conn, embedder, reranker, m, cases)]
    finally:
        conn.rollback()
        conn.close()
    with RUNS.open("w", encoding="utf-8", newline="\n") as f:
        f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in runs)
    section = table(summarise(runs, labels), datetime.now(UTC).isoformat(timespec="minutes"))
    print("\n" + section)
    if not a.case:
        write(section)
        print(f"\nWritten to {RESULTS.relative_to(ROOT.parent)}")


if __name__ == "__main__":
    main()
