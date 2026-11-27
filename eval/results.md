# Eval results

<!-- agent-eval:start -->
## Agent

36 hand-labelled chat turns (eval/convos.jsonl, labels in eval/agent_labels.jsonl), no fallback model. Run 2026-11-27T15:59+00:00 by `python -m eval.run_agent_eval`.

| Model | Tool accuracy | Argument accuracy | JSON valid | Invented jobs | p50 ms | p95 ms | Prompt tokens / turn |
| --- | --- | --- | --- | --- | --- | --- | --- |
| openai/gpt-oss-120b | 86% | 72% (25) | 100% | 0% | 13188 | 24330 | 2511 |
| qwen/qwen3.8-27b | 78% | 68% (25) | 100% | 3% | 21798 | 49049 | 3908 |

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

<!-- extract-eval:start -->
## Extraction

60 of 60 sampled jobs labelled by the owner (extract_sample.jsonl, extract_labels.jsonl). A field is correct when the extracted value equals the label, including both being "not stated".

| Field | all (n=60) | rules only (n=30) | rules + LLM (n=30) |
|---|---|---|---|
| seniority | 52% | 60% | 43% |
| min_exp_years | 78% | 97% | 60% |
| max_exp_years | 85% | 100% | 70% |
| work_mode | 48% | 70% | 27% |
| city | 98% | 100% | 97% |
| employment_type | 10% | 10% | 10% |
| skills precision | 83% | 78% | 90% |
| skills recall (owner-noticed misses) | 49% | 46% | 52% |

Skills were judged, not labelled blind: the owner saw the extracted list, marked wrong ones and added missing ones, so recall counts only the misses the owner noticed.

Caveat on work_mode and employment_type: the labeller showed the title, location and description, but not the boards' structured fields (Lever and Ashby send a workplace type and a commitment; Greenhouse sends a remote flag), which the extractor uses. The rules also default employment_type to full_time when nothing else is found. Of the employment_type misses, 54 of 54 are jobs the owner marked "not stated"; for work_mode it is 28 of 31. So those two rows mostly measure board metadata and the default against the description, not misread postings.
<!-- extract-eval:end -->
