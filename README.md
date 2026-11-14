# TradeOps Reconciler

**MongoDB *Agents in Context* Toronto — Track #3: Finish the Job**

TradeOps Reconciler investigates a rejected securities settlement instruction, verifies the correct receiving
account across three independent systems, gets a human to approve one exact amendment, submits it, and **proves
it took effect exactly once — even when the custodian's reply is lost and the worker crashes.**

> We don't just send the fix. We prove it happened once — even after the agent dies.

All data is synthetic. The broker, account directory and custodian are clearly labeled simulators with their own
SQLite stores. No real trades, transfers, accounts or settlement.

## The scenario

| System | Record |
|---|---|
| Broker | `TR-2041` BUY 100 XYZ @ CAD 42.50, portfolio `P-17`, EXECUTED |
| Custodian | `SI-2041` revision 1, REJECTED, safekeeping account `SAFE-100` |
| Account directory | `SAFE-100` retired, `SAFE-401` active for `P-17` |
| Goal | revision 2, `SAFE-401`, ACCEPTED — with exactly one custodian receipt |

## How it answers the track

1. **Effective vs. merely sent** — after `PATCH`, the worker reads the custodian's operation record and the
   instruction and checks ID, revision, account, status and receipt before calling it done.
2. **Resume without replay** — the approved payload and a stable `operationId` are written to MongoDB Atlas
   (majority write) *before* sending. A restarted worker resumes at verification with the same ID.
3. **Adapt to a changed system** — when the directory's response shape changes, Atlas Vector Search retrieves a
   verified past incident that points the agent to the live `/contract` endpoint and a validated adapter.
   Unknown shapes go to manual review.

## Architecture

React workbench → FastAPI API → MongoDB Atlas (cases, incidents + vector index, policies) ← workflow worker →
broker / directory / custodian simulators. See [docs/architecture.md](docs/architecture.md) and
[docs/api-contracts.md](docs/api-contracts.md).

## Run it locally

Requires Python 3.12 with [uv](https://docs.astral.sh/uv/) and Node 18+.

```bash
cp .env.example .env                       # fill in Atlas, Voyage, SIM_ADMIN_TOKEN, DEMO_REVIEWER_TOKEN
(cd backend && uv sync --extra dev)
./scripts/dev.sh                           # simulators on :8101/:8102/:8103, API on :8000
(cd frontend && npm install && npm run dev)   # workbench on http://localhost:3000
(cd backend && uv run pytest -m 'not atlas')  # offline tests
```

## Status

MongoDB foundation implemented: scoped PyMongo connections, strict case validation, unique indexes,
synthetic seeds, atomic stage/version/run updates, majority-written operation intent, recovery scans,
worker heartbeat helpers and real Atlas Vector Search integration. The organizer Sandbox is **Agents in
Context Toronto / Cluster0**. See [database setup](docs/mongodb-setup.md) for the current deployment state.

15 local tests and 8 live organizer Atlas tests passed, including checkpoint recovery in a new process.
Voyage is configured locally: 9 verified incidents have real 1024-dimensional embeddings; strict semantic
verification returns INC-004 first for the directory-field query. The API, actual workflow worker,
simulators and UI are still to build; the track behaviors above describe the intended complete product.
See [docs/AI_CONTEXT.md](docs/AI_CONTEXT.md) for the handoff.

Offline tests are isolated from exported application settings; Atlas tests retain real credentials.
Both modes have passed with API/database credentials exported in the test process.

## Configuration

Copy `.env.example` to `.env` and fill in values. Never commit `.env`.
This development machine already has generated credentials in its local `.env`; preserve them.

```bash
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install -e 'backend[dev]'
cd backend
.venv/bin/python scripts/setup_atlas.py
.venv/bin/python scripts/verify_atlas.py
.venv/bin/pytest -m 'not atlas' -q
RUN_ATLAS_TESTS=1 .venv/bin/pytest -m atlas -q
```

Setup uses the separate `MONGODB_SETUP_URI`; runtime and verification use `MONGODB_URI` (readWrite on
tradeops only). The current local key and semantic query are verified. On a new machine, add your own
`VOYAGE_API_KEY`, then run setup and
`.venv/bin/python scripts/verify_atlas.py --require-memory` to prove the real query returns INC-004 first.
Do not interpret a passing core database check as completed Vector Search or custodian crash recovery.

## Team / originality

Created during the hackathon by the team. All code and fixtures in this repository are original work from the event.
