# CLAUDE.md

TradeOps Reconciler — hackathon project (MongoDB *Agents in Context*, Track #3 "Finish the Job").
A control layer that lets AI agents fix bank back-office errors safely: approved exactly, executed once, proven.

**Start every session by reading `docs/AI_CONTEXT.md`** — current status, work split between the two lanes,
the agreed `db.py` / `memory.py` interface, rules, the Atlas setup checklist and the build order.
Design lives in `docs/architecture.md`; exact contracts in `docs/api-contracts.md`; demo in `docs/demo-script.md`.

**End every session by updating `docs/AI_CONTEXT.md`** §2 (status table) and §6 (session log) with what you
built, what you verified (and how), and any blockers. Keep `docs/api-contracts.md` in sync with any route change.

## Hard rules (details in AI_CONTEXT §3)

Synthetic data only · no Streamlit, not a dashboard · no LLM in MVP · only the worker calls custodian PATCH,
and only after exact-hash approval and a majority-written intent in Atlas · never fake results (show pending
states instead) · secrets only in `.env` (gitignored) · runtime DB access via PyMongo, not MCP.

## Stack and ports

| Process | Port | Start |
|---|---|---|
| Broker / directory / custodian simulators | 8101 / 8102 / 8103 | `./scripts/dev.sh` (starts all three + API) |
| FastAPI API | 8000 | `./scripts/dev.sh` |
| Workflow worker | — | `scripts/worker.sh` (not built yet) |
| React + Vite workbench | **3000** | `cd frontend && npm run dev` (proxies `/api` → :8000) |

Python 3.12 + uv + FastAPI + PyMongo + httpx in `backend/`; React 18 + Vite 5 + TS in `frontend/`.
Simulators are `--factory` apps (`simulators.<name>:create_app`) with their own SQLite files in `backend/simulators/data/`.

## Commands

```bash
cd backend && uv sync && uv run pytest     # install + tests
cd frontend && npm install && npx tsc -b --noEmit   # install + typecheck
```

## Branches

`main` (merged work) · `simulators` (app lane: simulators, API routes, frontend) · `db-setup` (DB lane:
`app/db.py`, `app/services/memory.py`, `scripts/setup_atlas.py`). Don't edit the other lane's files.
