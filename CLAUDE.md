# CLAUDE.md

TradeOps Reconciler — hackathon project (MongoDB *Agents in Context*, Track #3 "Finish the Job").

**Start every session by reading `docs/AI_CONTEXT.md`** — it has current status, rules, the Atlas setup checklist
and the build order. Design lives in `docs/architecture.md`; exact contracts in `docs/api-contracts.md`.

**End every session by updating `docs/AI_CONTEXT.md`** §2 (status table) and §6 (session log) with what you
built, what you verified (and how), and any blockers.

Hard rules (details in AI_CONTEXT §3): synthetic data only · no Streamlit, not a dashboard · no LLM in MVP ·
only the worker calls custodian PATCH, and only after exact-hash approval and a majority-written intent in Atlas ·
never fake results · secrets only in `.env` · runtime DB access via PyMongo, not MCP.

Stack: Python 3.12 + uv + FastAPI + PyMongo + httpx (backend, simulators, worker); React + Vite + TS (frontend).

MongoDB foundation is implemented. Read `docs/mongodb-setup.md` before changing database code:
`backend/app/{config,models,hashing,db,schema,seed}.py` and `backend/app/services/memory.py`.
Use `CaseStore.cas_update` with caseId, runId, stage and version; `persist_intent` must return an
acknowledged majority+j checkpoint before the worker sends anything. Its caller must first perform
the live custodian/directory checks. Runtime uses the readWrite-only user; setup uses the separate
`MONGODB_SETUP_URI` with dbAdmin on tradeops. Never log either URI or any key.

Organizer Atlas confirmed: **Agents in Context Toronto**, Sandbox project `6af899b4fb07f6aa867aa481`,
existing **Cluster0** (M10, AWS US_WEST_1, MongoDB 9.0.7). Reuse it; see deployment status in mongodb-setup.md.
The earlier free development cluster in SettleFlow 2.0 is retained; do not delete it during migration.
Organizer vector index is READY/queryable with 9 verified Voyage embeddings (voyage-3.5-lite, 1024 dims).
Real semantic retrieval is verified: the directory-field query returns INC-004 first. Vector queries use
local read concern because Atlas rejects majority for $vectorSearch; case reads/writes retain majority.
The database layer does not implement the HTTP API, actual worker, or custodian exactly-once proof.
Three groupmates have Atlas Project Data Access Read/Write membership; personal driver credentials and
per-machine network access are separate. See `docs/mongodb-setup.md` before changing team access.

Verified against organizer Cluster0: all 23 tests passed. Checks: `cd backend && .venv/bin/pytest -m 'not atlas'` (15 tests),
`RUN_ATLAS_TESTS=1 .venv/bin/pytest -m atlas` (8 live database tests),
`.venv/bin/python scripts/verify_atlas.py --require-memory` (passed with a real Voyage query). Tests delete only their own uniquely scoped synthetic
records in tradeops; current credentials deliberately cannot access arbitrary test databases.

`backend/tests/conftest.py` clears exported application settings only for offline tests, which also use
`Settings(_env_file=None)`. Tests marked `atlas` keep real environment/.env access. Do not remove runtime
environment loading to make a unit test pass; demo configuration must continue to use the real credentials.

## Ports and running (app lane)

| Process | Port | Start |
|---|---|---|
| Broker / directory / custodian simulators | 8101 / 8102 / 8103 | `./scripts/dev.sh` (starts all three + API) |
| FastAPI API | 8000 | `./scripts/dev.sh` |
| Workflow worker | — | `scripts/worker.sh` (not built yet) |
| React + Vite workbench | **3000** | `cd frontend && npm run dev` (proxies `/api` → :8000) |

Install and test: `cd backend && uv sync --extra dev && uv run pytest -m 'not atlas'`;
frontend: `cd frontend && npm install && npx tsc -b --noEmit`. Simulators are `--factory` apps
(`simulators.<name>:create_app`) with their own SQLite files in `backend/simulators/data/` (gitignored).

