# casano-agentbench

A benchmarking platform for AI agents, built for the HackCulture Global AI
Hackathon (Bifrost track). Team **Casano** (solo: Ankush Singh).

It runs agents against a fixed set of deterministic tasks, scores each
attempt with pure deterministic checkers, stores every run in SQLite, and
shows a leaderboard aggregated only from stored runs. No scores are ever
invented: when an agent fails, the failure is recorded as an error and the
output is left empty.

## What is real vs fallback

| Piece | Status |
| --- | --- |
| 5 deterministic tasks + checkers | Real, implemented and tested |
| EchoAgent / RuleAgent baselines | Real, run locally with no gateway |
| SQLite run storage + leaderboard | Real, aggregated only from stored runs |
| BifrostAgent (OpenAI-compatible POST) | Implemented, **tested against mocked HTTP only** |
| Live Bifrost gateway round-trip | **NOT verified.** No provider keys exist for this project, so no live gateway call was ever made. See "Bifrost configuration" below. |

When no gateway is running, the `bifrost` agent records a connection error
for each task (score 0) instead of producing output. The dashboard shows
"Bifrost: not configured" unless `BIFROST_BASE_URL` or `BIFROST_API_KEY` is
set; that pill reflects environment presence only and never exposes a key.

## Architecture

```
web/        Next.js 14 App Router + TypeScript, plain CSS (no Tailwind)
  app/page.tsx            Dashboard: tasks, agent selector, run, results,
                          history, leaderboard, Bifrost status pill
  app/runs/[id]/page.tsx  Run detail view
  lib/api.ts              Typed API client (NEXT_PUBLIC_API_URL)

backend/    FastAPI + pydantic v2 + httpx, stdlib sqlite3 (no ORM)
  app/main.py     HTTP API + CORS + input bounds
  app/tasks.py    5 tasks + pure deterministic checkers
  app/agents.py   Agent protocol, Echo/Rule/Bifrost agents, tool-loop
  app/tools.py    Fake tools: safe AST calculator (never eval()), KV lookup
  app/storage.py  SQLite: runs + results tables, leaderboard aggregation
  tests/          pytest suite (76 tests)
```

Runs are synchronous and bounded: at most 20 tasks per run, 30s timeout
per gateway request, at most 4 tool-loop steps per task.

## Tasks and scoring

Every checker is a pure function returning a score in 0..1 plus detail
strings. No LLM judges anything.

1. **arithmetic-01** — profit word problem; passes only on the exact
   numeric answer (156).
2. **json-extraction-01** — output must parse as JSON with `name`
   (string), `age` (integer), `city` (string). Partial credit per field.
3. **instruction-following-01** — output must contain `blue` and `waves`
   and must not contain `red` (forbidden token halves the score).
4. **tool-use-01** — agent must call the fake `calculator` tool for
   `17 * 6` (= 102) and then the fake `lookup` tool for
   `capital_of_france` (= Paris), via ```` ```tool ```` JSON blocks, in
   that order, and mention both results.
5. **summary-01** — summary must be 20–40 words and mention
   `photosynthesis`, `sunlight`, and `oxygen`.

## Run the backend

Requires Python 3.12. All commands below were run and verified on
17 Nov 2026.

```bash
cd backend
python3 -m venv .venv
# NOTE: /tmp on some VMs is a small tmpfs; point pip's temp dir elsewhere.
TMPDIR=~/workspace/.pip-tmp .venv/bin/pip install --no-cache-dir -r requirements.txt
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Health check: `curl http://127.0.0.1:8000/health` → `{"status":"ok"}`.

The SQLite file is created at `backend/data/agentbench.db` (gitignored).
Override it with `AGENTBENCH_DB=/path/to/file.db`.

## Run the frontend

Requires Node.js 18+. The commands below were run and verified on
17 Nov 2026 (`npm run build` passes; production server serves `/` and
`/runs/[id]` with HTTP 200).

```bash
cd web
npm install
npm run dev        # development server on http://localhost:3000
```

Production:

```bash
cd web
npm run build
npm run start      # serves the production build on http://localhost:3000
```

The API base URL is `NEXT_PUBLIC_API_URL` (default
`http://localhost:8000`), baked in at build time for production builds.

## Bifrost configuration

Bifrost (maximhq/bifrost, Apache 2.0) is an OpenAI-compatible LLM
gateway. Docs: https://docs.getbifrost.ai. Start a local gateway with
either:

```bash
npx -y @maximhq/bifrost
# or
docker run -p 8080:8080 maximhq/bifrost
```

Then configure the backend (copy `.env.example` to `.env`, or export the
variables):

```bash
BIFROST_BASE_URL=http://localhost:8080   # default if unset
BIFROST_MODEL=openai/gpt-4o-mini          # default if unset
BIFROST_API_KEY=                          # optional Bearer token
```

The agent POSTs OpenAI chat-completions JSON to
`{BIFROST_BASE_URL}/v1/chat/completions`. If the model output contains
```` ```tool ```` JSON blocks, the fake tools are executed locally and the
results are fed back, for at most 4 steps.

**Verification status (honest):** the gateway start commands and endpoint
shape above come from Bifrost's public docs, verified by reading them on
17 Nov 2026. The integration itself was tested only against mocked HTTP
(success, timeout, HTTP 500, empty choices, tool loop, auth header). No
live gateway run was performed, because no provider API keys exist for
this project. The first live run against a real gateway is still
unverified.

The Bifrost HTTP client ignores proxy environment variables
(`trust_env=False`): the gateway is expected to be local, and a malformed
proxy variable must not break or redirect the request. Client
construction failures are recorded as run errors, never crashes.

## API reference

| Method | Path | Description |
| --- | --- | --- |
| GET | `/health` | `{"status": "ok"}` |
| GET | `/tasks` | The 5 tasks (id, name, category, description, prompt) |
| GET | `/agents` | Agents + `bifrost_configured` (env presence only; no keys) |
| POST | `/runs` | `{"agent": "echo"\|"rule"\|"bifrost", "task_ids": [...]}`; runs synchronously, returns the stored run (201) |
| GET | `/runs` | Run summaries (newest first) |
| GET | `/runs/{id}` | Full run with per-task results (404 if unknown) |
| GET | `/leaderboard` | Per-agent aggregates from stored runs only; `[]` when none |

Example:

```bash
curl -X POST http://127.0.0.1:8000/runs \
  -H 'Content-Type: application/json' \
  -d '{"agent": "rule", "task_ids": ["arithmetic-01"]}'
```

## Security notes

- Pydantic input bounds: agent name allowlist (`echo`, `rule`,
  `bifrost`), max 32 chars; `task_ids` max 20, each max 64 chars and must
  be a known task id; unknown fields rejected.
- Timeouts on all external HTTP (30s per gateway request).
- CORS restricted to `http://localhost:3000` and `http://127.0.0.1:3000`
  by default; override with `CORS_ORIGINS`.
- The calculator is a safe AST evaluator: arithmetic only, no names,
  calls, attributes, or imports. `eval()` is never used anywhere.
- No shell execution anywhere in the backend.
- `.env` files are gitignored; `.env.example` holds placeholders only.
- `GET /agents` reports Bifrost configuration from environment-variable
  presence only and never returns key material (covered by a test).

## Tests

```bash
cd backend
.venv/bin/python -m pytest -q
```

76 tests, all passing (17 Nov 2026). Coverage: every checker pass +
fail, calculator injection rejection, Echo/Rule agents, BifrostAgent
with mocked httpx (success, timeout, HTTP error, empty choices, tool
loop, auth header, client-construction failure), and API endpoints via
TestClient (happy paths, validation errors, leaderboard empty + after
runs). One benign warning comes from Starlette's TestClient deprecating
httpx in favour of httpx2; it does not affect the tests.

## Limitations

- Runs are synchronous: a `POST /runs` with the `bifrost` agent blocks
  until every task finishes (bounded by the 30s timeout × 5 steps).
- Single-process SQLite storage; no auth, no multi-user support. This is
  a local hackathon demo, not a hosted service.
- The task set is fixed at 5 built-in tasks; there is no task-upload API.
- Bifrost integration is mock-tested only (see above).
- Scores measure narrow, deterministic behaviours. They say nothing
  about general agent quality.
