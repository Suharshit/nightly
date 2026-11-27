# Eval results

<!-- agent-eval:start -->
## Agent

36 hand-labelled chat turns (eval/convos.jsonl, labels in eval/agent_labels.jsonl), no fallback model. Run 2026-11-26T19:05+00:00 by `python -m eval.run_agent_eval`.

| Model | Tool accuracy | Argument accuracy | JSON valid | Invented jobs | p50 ms | p95 ms | Prompt tokens / turn |
| --- | --- | --- | --- | --- | --- | --- | --- |
| openai/gpt-oss-120b | 78% | 68% (25) | 89% | 3% | 12050 | 23563 | 1984 |
| qwen/qwen3.8-27b | 69% | 60% (25) | 100% | 3% | 21274 | 23579 | 2798 |

Invented jobs = share of turns where the reply named a job no tool returned (the guardrail removed it before the user saw it). Latency includes waiting for Groq's free-tier limit of 8K tokens a minute: with no fallback model, a turn that hits it waits up to 20 s, so p50/p95 measure the free tier more than the model.
<!-- agent-eval:end -->

<!-- search-eval:start -->
## Search

Snapshot frozen 2026-11-25T18:33+00:00 (1798 active jobs). 50 queries, 1825 hand labels. Run 2026-11-27T15:10+00:00 by `python -m eval.run_search_eval`.

| Variant | NDCG@10 | Recall@30 | MRR | judged@10 | p50 ms |
| --- | --- | --- | --- | --- | --- |
| keyword only | 0.564 | 0.721 | 0.797 | 1.000 | 102 |
| vector only | 0.574 | 0.653 | 0.832 | 1.000 | 105 |
| hybrid RRF | 0.633 | 0.861 | 0.882 | 1.000 | 116 |
| hybrid + rerank | 0.689 | 0.867 | 0.882 | 1.000 | 634 |
| + freshness & diversity | 0.611 | 0.878 | 0.820 | 0.996 | 617 |
<!-- search-eval:end -->
