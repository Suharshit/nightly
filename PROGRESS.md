# Progress

## Wed 25 Nov 2026

- Done: brief verified (endpoints, Groq models), model swap agreed, repo scaffold, CI, schema, 3 adapters, 108 companies, first ingest. 1,814 active India/remote jobs; re-run inserts 0.
- Done (evening): Supabase project `nightly` (free, ap-southeast-1), migrations 001–003 applied, RLS on every table, anon has no table access. First Supabase ingest: 108 boards ok, 0 failed, 1,798 jobs inserted from 107 companies. GitHub secrets DATABASE_URL and GROQ_API_KEY set.
- Done (night): embed.py (PR #4, runs nightly). Supabase extraction backfill: rules 1,108 + qwen2.5:3b on Actions 689 = 1,797/1,798 extracted (1 failed); main run took 29–47 min per shard, 0 Groq tokens. All 1,798 embedded in 156 s (local CPU). Embedding dedupe found 0 (no company on two ATS).
- Broken: backfill.yml "empty = all" ran 10 per shard (GitHub uses the default); fixed to "0 = all".
- Broken: the university network intercepts HTTPS (curl and Docker fail; Python works, and the hotspot works).
- Next: Thu. Extraction backfill plan (no Ollama on an 8 GB laptop), extract.py, embed.py, hybrid /matches.
