# Progress

## Wed 25 Nov 2026

- Done: brief verified (endpoints, Groq models), model swap agreed, repo scaffold, CI, schema, 3 adapters, 108 companies, first ingest. 1,814 active India/remote jobs; re-run inserts 0.
- Done (evening): Supabase project `nightly` (free, ap-southeast-1), migrations 001–003 applied, RLS on every table, anon has no table access. First Supabase ingest: 108 boards ok, 0 failed, 1,798 jobs inserted from 107 companies. GitHub secrets DATABASE_URL and GROQ_API_KEY set.
- Done (night): embed.py (PR #4, runs nightly). Supabase extraction backfill: rules 1,108 + qwen2.5:3b on Actions 689 = 1,797/1,798 extracted (1 failed); main run took 29–47 min per shard, 0 Groq tokens. All 1,798 embedded in 156 s (local CPU). Embedding dedupe found 0 (no company on two ATS).
- Broken: backfill.yml "empty = all" ran 10 per shard (GitHub uses the default); fixed to "0 = all".
- Broken: the university network intercepts HTTPS (curl and Docker fail; Python works, and the hotspot works).
- Next: Thu. Extraction backfill plan (no Ollama on an 8 GB laptop), extract.py, embed.py, hybrid /matches.

## Thu 26 Nov 2026 (started Wed night)

- Done: /matches (PR #6): hard filter + keyword top 50 + vector top 50 + RRF. scripts/time_matches.py, warm: local DB p95 75 ms, Supabase from the laptop p95 474 ms (target 1.5 s). Resume upload: POST /resume (PDF → text → 12–20 rules skills → bge query vector → profiles), GET /me, Supabase token check via /auth/v1/user (cached). Migration 004 (profiles.resume_skills) on local + Supabase. eval/queries.jsonl: 50 proposed queries, unlabelled.
- Broken: qwen2.5:3b seniority labels look off in spots ("Intermediate Backend Engineer" → intern). No reranker yet, so non-engineering interns rank for "frontend react intern".
- Next: Fri. Reranker, personalisation, diversity, reasons; agent loop; freeze the eval snapshot; label.py so the owner can label the queries; run_search_eval.py.

## Fri 27 Nov 2026 (started Thu night)

- Done: cross-encoder reranker (ms-marco-MiniLM-L-6-v2) on the fused top 30, switchable with rerank=false. Search now runs as one SQL round trip. scripts/time_matches.py against Supabase from the laptop, warm: rerank on p50 836 / p95 924 ms; rerank off p50 128 / p95 142 ms (was p95 474 with three queries).
- Broken: for "frontend react intern" only one result is relevant; the index has few frontend internships, so the rest are weak whatever the order.
- Done: personalisation (brief weights: rerank 1.0, taste 0.3, skill Jaccard 0.2, freshness 0.1, dislike penalty −0.5), max 2 per company in any 5, data-built reasons, query-less feed from the resume, POST /feedback (like moves taste 20%, dislike reasons become avoid rules), PATCH /prefs, shown logging and exclusions. Local check with a throwaway user: one like took the liked job from 0.12 to 0.42 and the disliked job left the feed. Anonymous /matches on Supabase: p50 840 / p95 1080 ms.
- Broken: signed-in timing on Supabase not measured (needs a real Supabase user, so the web app). A job shown 3 times is hidden, so 3 feed refreshes rotate the top matches; revisit once real users try it.
