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
| Repo | MongoDB runtime modules, setup/verification scripts and tests added; docs and fixtures retained. |
| Simulators (broker/directory/custodian) | **Built + tested** (merged from branch `simulators`). Separate FastAPI processes with own SQLite files; custodian idempotency (key checked before revision, amendment + receipt in one transaction), lost-response and operations-unavailable faults, `/admin/proof`. Lost-response verified against real processes. |
| Backend API + worker | Database foundation implemented. API routes built: `GET /api/health` (Atlas ping, worker heartbeat from `workers`, memory status via `IncidentMemory.status()`), `GET /api/cases/{id}/sources`, `/api/demo/{reset,state,faults,directory-version,custodian-proof}`. **Not built:** case routes (`/cases/{id}`, investigate/approve/execute/timeline), the workflow worker, investigation, approvals, verification. |
| Atlas Sandbox | Organizer confirmed: Agents in Context Toronto, project 6af899b4fb07f6aa867aa481, Cluster0 (M10/AWS US_WEST_1/MongoDB 9.0.7). Live setup and runtime verification passed; current .env rechecked with both runtime/setup connections successful; targets organizer Cluster0. See mongodb-setup.md. |
| Development Atlas | SettleFlow 2.0 / tradeops-sandbox (Free/M0, AWS US_EAST_1, MongoDB 8.0.37): verified development environment retained; active runtime now uses organizer Cluster0. |
| Vector Search | **Verified on organizer Cluster0:** READY index; 9 verified incidents embedded with Voyage voyage-3.5-lite, 1024 dims. Real query returns INC-004 first (score ~0.800), suggesting GET_DIRECTORY_CONTRACT. Unverified INC-010 excluded. |
| Frontend workbench | **Shell built** (`frontend/`, React 18 + Vite 5 + TS, **http://localhost:3000**). Live source cards, failure lab, proof panel from real API reads. Investigation/approval/timeline show an honest pending state and only poll `/api/cases/{id}` once health reports Atlas connected. |
| Team Atlas access | Three groupmates added to the organizer Sandbox with Project Data Access Read/Write, verified in the Atlas users list. Personal driver credentials/IP access are separate. |
| Tests | All 23 tests passed against organizer Cluster0 (15 local + 8 real Atlas), including with credentials exported. Offline settings tests are isolated from shell variables (P2 fixed). Strict runtime verification including real semantic retrieval passed. Full worker/custodian crash recovery not yet built/tested. After merging the app lane: **33 offline tests pass** (`uv run pytest -m 'not atlas'`: 15 DB-lane + 18 simulator/idempotency); live Atlas tests not re-run on Harshi's Mac (no credentials there). |

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

## 4. Database setup and remaining checks

Read `docs/mongodb-setup.md` for resources, modules, verification and migration instructions.
The user initially authorized SettleFlow 2.0, then found the actual organizer invitation and Sandbox project.
Organizer org **Agents in Context Toronto** is now confirmed in MCP (`69ef9daf03d2ce35c2657862`).
Reuse its existing **Cluster0**; do not provision an extra paid cluster.

Database modules and scripts already exist. Setup creates cases/incidents/policies/workers, strict case
validation, unique case/partial operation/incident/policy indexes, a stage index and a real vector index.
It preserves live cases/policies and embeds only the 9 verified incidents when a key exists.
Runtime `tradeops-app` has readWrite on tradeops only; setup `tradeops-setup` adds dbAdmin on that DB only.
Both are scoped to the selected cluster. Credentials are only in gitignored `.env` (0600).

Confirmed: local `.env` targets organizer Cluster0 and setup plus runtime verification succeeded there.

Voyage is now verified: local .env key loaded successfully, 9 real document embeddings stored, and
`verify_atlas.py --require-memory` passed. The query “directory payload moved the account field” returns
INC-004 first (~0.800), then INC-008 and INC-005. Suggested read-only action: GET_DIRECTORY_CONTRACT.
Use `ReadConcern("local")` only for the $vectorSearch aggregation: Atlas rejects majority for this stage.
Case and checkpoint reads/writes retain their majority settings. A regression test enforces this boundary.

Remaining application integration:
1. Wire `CaseStore` and `IncidentMemory` into the API/worker; implement live pre-send checks and
   independent custodian verification. Retrieval is real, but the worker has not consumed it yet.
2. On a new machine, provide your own gitignored Voyage/Atlas credentials, run setup and
   `.venv/bin/python scripts/verify_atlas.py --require-memory`. Reuse stored embeddings when unchanged.
3. Never present database durability/retrieval checks as the full exactly-once application demonstration.

## 5. Build order for the application (Phases)

1. **Simulators** (`backend/simulators/`): `common.py` (SQLite helper, fixture loading, admin-token check),
   `broker.py`, `directory.py`, `custodian.py`, `seed.py`. Each is its own FastAPI app/process (ports 8101/8102/8103),
   DB file under `backend/simulators/data/`. Custodian PATCH exactly per `architecture.md` §9.
   → `tests/test_idempotency.py` (TestClient, no Mongo): same key+payload → same receipt; different payload → 409;
   known key checked before stale revision; lost-response fault still commits; proof counts.
2. **Backend core**: `app/config.py`, `db.py`, `schema.py`, `seed.py`, `hashing.py`, `models.py`
   and `services/memory.py` already exist. Reuse `CaseStore.cas_update` (requires run_id), `persist_intent`,
   `list_resumable`, `heartbeat`, and `IncidentMemory.retrieve`. Remaining application modules:
   `services/simulator_clients.py`, `directory_adapters.py`, `investigation.py`, `approvals.py`,
   `workflow.py`, `verification.py`, `worker.py`, `routes/{cases,demo,health}.py`, `main.py`.
3. **Application tests with Mongo**: current users are restricted to tradeops. Use unique synthetic records
   and exact cleanup as in `tests/test_atlas.py`; never drop the database. Still build approval endpoint guards,
   directory contract tests, happy path and full crash recovery with real worker/simulator subprocesses
   (worker exits 137 → Atlas AWAITING_VERIFICATION → restart → VERIFIED; one receipt/PATCH/revision increment).
4. **`backend/scripts/setup_atlas.py` and `verify_atlas.py` already implemented** (§4).
5. **Frontend** (`frontend/`, React 18 + Vite 5 + TS): components listed in `architecture.md` §5; dark navy,
   teal success, amber/red exceptions; every value from the API; loading/error/manual-review states; keyboard accessible.
6. **Scripts + README**: `scripts/dev.sh`, `worker.sh`, `kill-worker.sh`, `reset.sh`; runnable instructions.

## 6. Session log (append, newest last)

- **2026-11-14 — init session (Claude Code, Harshi's Mac).** Repo was empty on GitHub. Created docs
  (architecture, API contracts, demo script, this file), `CLAUDE.md`, README, `.env.example`, `.gitignore`,
  canonical fixtures. Decisions: no LLM for MVP; Voyage AI embeddings; Atlas set up in a teammate's session;
  no local Docker DB. No application code written yet — next agent starts at §5 step 1.

- **2026-11-14 — MongoDB setup (Codex).** Read blueprint, master brief, guidance and fixtures. Created
  authorized development cluster tradeops-sandbox in SettleFlow 2.0, scoped users and this Mac's IP entry.
  Implemented PyMongo config/models/hashing, atomic transitions with run/version guards, majority+j intent,
  recovery scans, heartbeat, schema/index setup, safe seeds, real Voyage/Vector Search pending/disabled states,
  setup and verification CLIs. Seeded 1 case, policy v1, 10 incidents; development vector index READY.
  Ruff passed; 14 local + 8 real development Atlas tests passed. New subprocess recovered identical operation
  intent; actual worker/custodian recovery remains unbuilt. User then located organizer Sandbox: confirmed
  Agents in Context Toronto and project 6af899b4fb07f6aa867aa481, reusing existing Cluster0. Provisioned scoped
  organizer users/network access; installed collections/validators/indexes/seeds and switched local .env.
  All 22 tests (14 local + 8 real Atlas) and the runtime verification passed against organizer Cluster0.
  Organizer cluster IDLE; vector index READY/queryable; rerunning setup preserved canonical NEW case/version 1.
  Original development cluster retained. Missing Voyage key blocks embeddings/ranking.
  Updated CLAUDE.md, README, .env.example and docs. Next application work: §5 step 1.

- **2026-11-14 — .env connection recheck (Codex).** Confirmed both current runtime and setup credentials
  connect to organizer Cluster0/tradeops. Vector index READY/queryable, 1 synthetic case, 0 embeddings,
  no worker heartbeat. Added explicit MONGODB_TIMEOUT_MS=10000 and MONGODB_VECTOR_INDEX=incident_vector_index
  to the local .env, matching existing code defaults. Voyage key remains absent; simulator/reviewer tokens
  remain example placeholders. Broker/directory/custodian health ports are not reachable; those services and
  the worker are still unbuilt. No credentials printed or committed; .env remains mode 0600 and gitignored.

- **2026-11-14 — Voyage activation and live retrieval (Codex).** After the user saved their key in the
  root .env, the app loaded it and Voyage generated all 9 verified incident vectors (voyage-3.5-lite,
  document input, 1024 dims). INC-010 remains unembedded. The first real search exposed Atlas error 72:
  $vectorSearch rejects majority read concern. Fixed only the aggregation's collection options to local;
  majority case reads/writes remain unchanged. Added a regression test covering read concern and metadata
  filters. Strict verification passed with a real query embedding: “directory payload moved the account
  field” returned INC-004 first, score 0.799821, next check GET_DIRECTORY_CONTRACT (then INC-008, INC-005).
  All 23 tests (15 local + 8 real Atlas) passed; Ruff passed. Updated CLAUDE.md, README and docs. API,
  worker, directory adaptation and the full custodian recovery demo remain application work. No key printed.

- **2026-11-14 — Team Atlas access (Codex).** Added all three user-specified groupmates to the organizer
  Sandbox project with Project Data Access Read/Write, after confirmation of the exact recipients and role.
  Atlas reported three invitations and listed all three with the intended project role. No organization-wide
  administrator rights, personal database logins, or additional IP entries were created. Updated setup/handoff
  docs without publishing teammate email addresses in the repository. No application code changed.

- **2026-11-14 — P2 test environment isolation (Codex).** Added tests/conftest.py: offline tests clear
  application settings from their temporary process environment; atlas-marked tests keep real settings.
  The existing _env_file=None still disables unit-test dotenv loading. All 15 offline tests passed with
  deliberately conflicting exported Voyage/model/memory/database settings. All 23 tests then passed with
  real credentials exported, including 8 live Atlas tests. Ruff/format/whitespace checks passed. Runtime
  config and the local .env were not changed; this fix affects test reliability, not the demo workflow.
  P2 review finding resolved. No commit or push performed.
- **2026-11-14 — merge of `simulators` with `main` (Claude Code, Harshi's Mac).** Took Keerat's version of every
  conflicting file (config, pyproject, conftest, CLAUDE.md, README, this file). Added to Keerat's `Settings`
  (additive only): `demo_case_id`, `broker_url`, `directory_url`, `custodian_url`, `sim_admin_token` (SecretStr),
  `custodian_timeout_seconds`, `worker_poll_seconds`, plus `get_settings()`. pyproject: hatch packages now
  `app` + `simulators`, pytest `pythonpath = ["."]`, explicit `python-dotenv`. conftest: simulator fixtures appended
  (they set their own `SIM_ADMIN_TOKEN` because the autouse fixture clears settings env vars). `/api/health` now
  uses `create_client`/`get_database`, the `workers` heartbeat doc and `IncidentMemory.status()` (cached 30 s).
  Install with `cd backend && uv sync --extra dev`. Next: case routes + worker using `CaseStore`.
