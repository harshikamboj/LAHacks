# AI_CONTEXT — handoff for the next coding agent

> **Keep this file updated.** Every agent session that changes the project must update §2 (status) and §6 (log)
> before ending. Teammates hand work between devices/sessions using this file.

## 1. Read these first (in order)

1. `docs/architecture.md` — design, MongoDB schema, state machine, recovery table, idempotency contract.
2. `docs/api-contracts.md` — exact routes, payloads, error codes for simulators and API.
3. `docs/demo-script.md` — what judges must see; build toward it.
4. `backend/fixtures/*.json` — canonical synthetic data (IDs are fixed; don't rename).

The original spec documents (*Master Build Brief*, `TradeOps_Reconciler_Blueprint.docx`) are not in the repo;
everything binding from them is captured in `docs/architecture.md`.

## 2. Current status (update me)

| Area | Status |
|---|---|
| Repo | `main` has the init docs. Branch **`simulators`** has everything below (not yet merged). |
| Simulators (broker/directory/custodian) | **Built + tested.** `backend/simulators/`. 18 pytest tests pass (`cd backend && uv run pytest`). Lost-response fault verified against real processes: caller times out, custodian commits once, same-key replay returns the original receipt. |
| API (`backend/app/`) | **Partial.** Built: `config.py`, `errors.py`, `services/simulator_clients.py`, routes `GET /api/health`, `GET /api/cases/{id}/sources`, `/api/demo/{reset,state,faults,directory-version,custodian-proof}`. **Not built:** case routes (`/cases`, `/cases/{id}`, investigate/approve/execute/timeline), worker, investigation, approvals, workflow, verification, directory adapters. |
| Atlas Sandbox | **Not set up.** DB lane (teammate). `app/db.py`, `app/services/memory.py`, `backend/scripts/setup_atlas.py` not written yet. |
| Vector Search | Not set up. Needs `VOYAGE_API_KEY` + Atlas index (§4). |
| Frontend workbench | **Shell built** (`frontend/`, React 18 + Vite 5 + TS). Live source cards, failure lab (lost response, ops unavailable, directory v1/v2/v3, reset), proof panel — all from real API reads. Investigation/approval/timeline show an honest "case engine not connected" state and only poll `/api/cases/{id}` once `/api/health` reports Atlas connected. |
| Tests | Simulator + custodian idempotency tests done. Mongo-backed tests (approval guards, happy path, crash recovery) not started. |

### Work split (two lanes, no shared files)

| Lane | Owner | Files |
|---|---|---|
| **DB lane** | teammate (branch `db-setup`) | `backend/app/db.py`, `backend/app/services/memory.py`, `backend/scripts/setup_atlas.py`, Atlas Sandbox + Voyage key |
| **App lane** | Harshi (branch `simulators`) | `backend/simulators/*`, `backend/app/{config,errors,main}.py`, `backend/app/routes/*`, `backend/app/services/simulator_clients.py`, `frontend/*`, `scripts/*` |
| **Shared next** | whoever is free first, after both merge | `backend/app/worker.py`, `services/{investigation,approvals,workflow,verification,directory_adapters}.py`, `routes/cases.py` |

### Interface the DB lane must provide (agreed — don't change without updating this file)

```python
# backend/app/db.py  — reads settings from app.config.get_settings() (mongodb_uri, mongodb_db)
def ping() -> None: ...                       # raises on failure; used by GET /api/health
def get_db() -> "pymongo.database.Database": ...
def ensure_indexes() -> None: ...             # idempotent; normal indexes only (vector index lives in setup_atlas.py)
def cas_update(case_id: str, from_stage: str, expected_version: int, to_stage: str | None = None,
               set_fields: dict | None = None, event: dict | None = None,
               majority: bool = False) -> dict | None: ...
    # find_one_and_update({caseId, stage: from_stage, version: expected_version},
    #   {$set: {stage: to_stage or from_stage, **set_fields, updatedAt}, $inc: {version: 1},
    #    $push: {events: {$each: [event], $slice: -100}}}) -> updated doc, or None if stale.
    # majority=True -> WriteConcern("majority", j=True) (used for the pre-send intent).

# backend/app/services/memory.py
def search(query: str, k: int = 3) -> dict: ...
    # {"status": "FOUND" | "PENDING" | "NONE", "matches": [{incidentId, title, score,
    #   suggestedNextCheck, verifiedResolution}], "reason": str | None}
    # PENDING (with reason) when VOYAGE_API_KEY / index / Atlas unavailable or MEMORY_ENABLED=false. Never fake.
```

### How to run what exists

```bash
cd backend && uv sync          # once
cp .env.example .env           # once, at repo root; set SIM_ADMIN_TOKEN, DEMO_REVIEWER_TOKEN, DEMO_MODE=true
./scripts/dev.sh               # broker :8101, directory :8102, custodian :8103, API :8000
cd frontend && npm install && npm run dev   # workbench on :3000 (proxies /api to :8000)
cd backend && uv run pytest    # tests
```

## 3. Non-negotiable rules (from the brief)

- Synthetic data only. Never connect to real brokers/banks/custodians or production systems.
- **No Streamlit. Not a dashboard.** One interactive case workbench where the agent workflow is the feature.
- No LLM in the MVP (team decision). Deterministic investigator + Atlas Vector Search precedents guide read-only tool choice.
- Nothing mutates the custodian before an exact-hash approval. Only the **worker** calls `PATCH`.
- Persist `operationId` + payload + stage `AWAITING_VERIFICATION` in Atlas (majority write) **before** sending PATCH.
- After an ambiguous outcome: never generate a new `operationId`, never blindly retry. Verify via custodian read-back.
- Unknown directory schema / conflicting evidence / unresolved ambiguity → `MANUAL_REVIEW`.
- Never fake anything: no hardcoded success in the UI, no fake retrieval results, no UI-only "crash". If a feature
  is blocked, mark it pending/feature-gated and say so.
- Runtime uses **PyMongo with the app's own credentials** (`MONGODB_URI`). MCP is for setup only.
- Secrets only in `.env` (gitignored). Never commit URIs, tokens, keys.
- Do not drop/delete anything in Atlas except the synthetic demo records; confirm destructive ops with a human.
- Priority: crash recovery + exactly-once proof (Phases 1–2) **before** Vector Search / directory adaptation (Phase 3).

## 4. Database-side checklist (for the teammate's Atlas session)

Target: organizer's **Atlas Sandbox** project/cluster. Verify it is the hackathon Sandbox before writing anything.

1. Create a database user for the app with readWrite on database `tradeops` only. Put the SRV URI in `.env` as
   `MONGODB_URI`, with `MONGODB_DB=tradeops`. Allow the team's IPs in the network access list.
2. Confirm privileges: insert/read a synthetic test doc in `tradeops.healthcheck`, then delete only that doc.
3. Once `backend/scripts/setup_atlas.py` exists, run it (idempotent):
   `cd backend && uv run python scripts/setup_atlas.py`. It must create:
   - collections `cases` (with `$jsonSchema` validator), `incidents`, `policies`, `workers`
   - indexes: `cases.caseId` unique; `cases.operation.operationId` unique partial (`$exists: true`); `cases.stage`; `incidents.incidentId` unique
   - Vector Search index `incident_vector_index` on `incidents` (definition in `architecture.md` §6)
   - seed `policies` from `fixtures/policies.json`; seed `incidents` from `fixtures/incidents.json` with Voyage
     embeddings (`voyage-3.5-lite`, `input_type=document`, 1024 dims) of `symptom + " " + verifiedResolution`.
   If the script doesn't exist yet, the same steps can be done via the MongoDB MCP / Atlas UI using those definitions.
4. Verify: a `$vectorSearch` for "directory payload moved the account field" returns `INC-004` first.
5. Verify majority write concern works (`WriteConcern("majority", j=True)` insert succeeds) and note the Atlas tier/version here.
6. Record results in §2 and §6 of this file: what exists, the tier, any permission blockers.

## 5. Build order for the application (Phases)

1. **Simulators** (`backend/simulators/`): `common.py` (SQLite helper, fixture loading, admin-token check),
   `broker.py`, `directory.py`, `custodian.py`, `seed.py`. Each is its own FastAPI app/process (ports 8101/8102/8103),
   DB file under `backend/simulators/data/`. Custodian PATCH exactly per `architecture.md` §9.
   → `tests/test_idempotency.py` (TestClient, no Mongo): same key+payload → same receipt; different payload → 409;
   known key checked before stale revision; lost-response fault still commits; proof counts.
2. **Backend core** (`backend/app/`): `config.py` (dotenv), `db.py` (client, `cas_update` transition helper,
   `ensure_indexes`), `hashing.py` (canonical sha256), `models.py` (stage enum, request bodies),
   `services/simulator_clients.py` (httpx, typed errors: `Unavailable`, `Timeout`, `HttpError`),
   `services/directory_adapters.py` (v1, v2; v3 unknown), `services/memory.py` (Voyage REST + `$vectorSearch`,
   returns `PENDING` with reason when unavailable; `MEMORY_ENABLED=false` for paired off/on run),
   `services/investigation.py`, `services/approvals.py`, `services/workflow.py` + `verification.py`, `worker.py`,
   `routes/{cases,demo,health}.py`, `main.py`.
3. **Tests with Mongo** (`MONGODB_URI` required; use a throwaway db name `tradeops_test_<random>` and drop only it):
   approval guards, directory contract (v1/v2/v3), happy path, and **crash recovery with real subprocesses**
   (worker exits 137 → Atlas shows AWAITING_VERIFICATION + same operationId → restart → VERIFIED; receipt count 1,
   PATCH count 1, revision 1→2).
4. **`backend/scripts/setup_atlas.py`** (§4).
5. **Frontend** (`frontend/`, React 18 + Vite 5 + TS): components listed in `architecture.md` §5; dark navy,
   teal success, amber/red exceptions; every value from the API; loading/error/manual-review states; keyboard accessible.
6. **Scripts + README**: `scripts/dev.sh`, `worker.sh`, `kill-worker.sh`, `reset.sh`; runnable instructions.

## 6. Session log (append, newest last)

- **2026-11-14 — init session (Claude Code, Harshi's Mac).** Repo was empty on GitHub. Created docs
  (architecture, API contracts, demo script, this file), `CLAUDE.md`, README, `.env.example`, `.gitignore`,
  canonical fixtures. Decisions: no LLM for MVP; Voyage AI embeddings; Atlas set up in a teammate's session;
  no local Docker DB. No application code written yet — next agent starts at §5 step 1.
- **2026-11-14 — app-lane session 1 (Claude Code, Harshi's Mac, branch `simulators`).** Built the three
  simulators (own SQLite each, `--factory` apps), custodian idempotency contract + faults + proof, 18 passing
  tests, API skeleton (health, live sources, demo controls), `scripts/dev.sh`, and the React workbench shell.
  Verified live: lost-response fault makes a 2 s client time out while the custodian commits exactly once;
  replay with the same key returns the original receipt; directory v1→v2 switch shows in the UI. Not built:
  case engine (worker, case routes, investigation, approvals) — waits on the DB lane's `db.py`.
  `docs/api-contracts.md` updated: operation 404 body shape, directory `AMBIGUOUS_ACTIVE_ACCOUNT`.
