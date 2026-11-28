# nightly

Mobile-first job-matching app for Indian students and freshers. The full spec is in [docs/BRIEF.md](docs/BRIEF.md). Progress notes are in [PROGRESS.md](PROGRESS.md).

## Hard constraints

- Budget is ₹0. Use free tiers only and never add a payment method.
- Open-weight models only: Groq free tier, with local Ollama as the fallback.
  - Agent: `openai/gpt-oss-120b`, with `qwen/qwen3.8-27b` as the agent-eval comparison.
  - Extraction and 429 fallback: `openai/gpt-oss-20b`.
  - The Llama 3.x models in the brief were shut down by Groq on 16 Aug 2026.
- Free limits per model (rate-limits docs, read 25 Nov 2026): 30 RPM, 1K RPD, 8K TPM, 200K TPD. Limits apply per organisation, so drive the limiter from the `x-ratelimit-*` headers.
- Data comes only from the public job-board APIs: Greenhouse, Lever and Ashby. No scraping of LinkedIn, Naukri or Indeed. Send 1 request/second with a User-Agent.
- No invented numbers. Every metric must come from a script or a log. Never create eval labels with an LLM; the owner labels.
- Ask before adding a paid service or a closed model, changing the stack, adding a dependency heavier than a few MB, or deleting data.
- Never commit `.env` or keys.

## Stack

- `web/`: Next.js 14 + Tailwind on Vercel
- `api/`: FastAPI + Pydantic v2 (Python 3.11 in Docker) on an HF Space
- `worker/`: ingest, extract, embed and digest jobs, run by GitHub Actions cron
- `db/migrations/`: Supabase Postgres with pgvector and tsvector
- Models: `BAAI/bge-small-en-v1.5` for embeddings and `cross-encoder/ms-marco-MiniLM-L-6-v2` for reranking, both on CPU

## Run commands

```sh
docker compose up -d db                    # local Postgres + pgvector, with migrations applied
.venv/Scripts/python -m pip install -r requirements-dev.txt
.venv/Scripts/python -m pytest
.venv/Scripts/python -m ruff check .
.venv/Scripts/python -m worker.ingest      # fetch all boards into DATABASE_URL (Supabase: live data)
.venv/Scripts/python scripts/check_slugs.py
```

Two databases in `.env`: `DATABASE_URL` is Supabase (live data and the `eval` snapshot the labels belong to), so ingest, `scripts.migrate`, the evals and a local API all act on it. `DATABASE_URL_LOCAL` is the Docker Postgres; `pytest` always uses it (`tests/conftest.py`) and refuses a non-local URL. To run the API or a script on the local DB, set `DATABASE_URL` to the local URL in that shell first.

## Cut order (first to go → last)

1. Email digest, replaced by "New since yesterday"
2. Personalisation simulation eval
3. Ashby adapter
4. Chat UI polish
5. Personalisation
6. The agent

Never cut ingestion, hybrid search + rerank, the search eval table, a public URL or real users.

## Working rules

- Build thin vertical slices and boring code. No agent frameworks.
- Keep `pytest` green before every commit, and make small commits.
- Push every night and update `PROGRESS.md` (done / broken / next).
- Local network note: the university network intercepts some HTTPS, so curl can fail with `SEC_E_UNTRUSTED_ROOT`. Python clients work.
