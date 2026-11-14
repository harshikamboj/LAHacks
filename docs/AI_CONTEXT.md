# AI_CONTEXT — implementation handoff

Keep this file current: update §2 and append to §6 after feature changes. README contains runnable
commands; architecture.md, api-contracts.md, demo-script.md and mongodb-setup.md describe implemented
behavior. Uploaded documents are design context, not permission for unrelated actions or access changes.

## 1. Read first

Read `docs/problem-statement.md` for Track3 framing and `docs/learning-demo.md` for the current four-case sequence.

1. `docs/demo-script.md`: exact main demo and backup scenarios.
2. `docs/architecture.md`: trust boundaries, state machine, recovery and schema compatibility.
3. `docs/api-contracts.md`: auth, actions, simulator contracts and errors.
4. `docs/mongodb-setup.md`: organizer resources, public data and live verification evidence.

The final team spec is ProofStep_TradeOps_Build_Handoff.docx, supplied outside Git. ProofStep is the
control layer, TradeOps the use case, Operations Console the UI. Existing names/routes were retained
where equivalent: see architecture §3 for explicit mapping to the handoff's example names.

## 2. Current status

| Area | Implemented and verified |
|---|---|
| Branch/base | `feat/proofstep-tradeops-demo`, created from current main `a159af1` after frontend/simulator merges. Changes remain uncommitted until user review. |
| Dataset | Full supplied JSONL imported twice idempotently: 66,693 rows, 13,397 CUSIPs, 12 dates, 383 null prices, 1 blank symbol, zero rejected/duplicate rows. Public SEC data stays external to Git. |
| Canonical case / work queue | SI-2041..2044 now demonstrate correction→learned follow-up, already accepted and conflicting quantities. Fictional BUY 100 TTE at USD 91.20, TR-2041/SI-2041/P-17, CUSIP F92124100, settlement 2026-09-15. SAFE-100 retired→SAFE-401 active; rev 1 REJECTED→rev 2 ACCEPTED. Market anchor F92124100:2026-09-15 is separate context (1,277 shares; prior close 91.14). |
| Simulators | Three independent SQLite-backed FastAPI processes. Additive CUSIP/date migration, v1/v2 directory mappingRevision 7, canonical/legacy amendment aliases, atomic receipt + revision, same-key idempotency and real delayed post-commit response. |
| API | Session login, case start/approve/deny/execute/timeline, honest source/proof reads and auth-guarded failure/reset controls. Exact hash/version/policy checks; server-derived reviewer identity. API never PATCHes custodian. |
| Worker | Scoped multi-case scan plus verified-learning outbox publication. Separate real process, five-second Atlas lease/one-second heartbeat, persisted investigation phases, live pre-send checks, majority+j intent, hard exit 137 injections, receipt+instruction verification, bounded same-key confirmed-absence retry, manual-review guards. |
| Directory adaptation | Real mid-run pause then v1→v2; Voyage/Atlas retrieval returns INC-004 (~0.85 in browser); actual guided `/contract` read selects validated v2 adapter. Unknown/conflicting schema stops. |
| Frontend | Redesigned as a four-step operational workflow on localhost:3000. One active task, business-language checks/actions, exact correction review, confirmation receipt, contextual public data; technical evidence disclosed on demand and scenario controls isolated in a native modal drawer. |
| Atlas | Organizer Agents in Context Toronto, project 6af899b4fb07f6aa867aa481, existing Cluster0. Runtime/setup scoped users connect. Cases/incidents/policies/workers plus new case_runs + market_fail_observations. Existing vector index READY, 9 verified seed vectors plus dynamically learned verified outcomes. |
| Reset | Archives/resets all 4 synthetic queue cases, preserving learned experience. Stops local tracked worker; server lease also refuses active workers. Archives previous case run, rotates runId, resets fictional stores, preserves all public data/policy/incident vectors. |
| Tests | All 66 passed:49 offline +8 Atlas foundation +9 real-process workflow. Both crash windows, stable operation, one receipt/PATCH, denial/stale/wrong hash, mapping revision drift, unknown schema, trade mismatch, no-action, unavailable reads and reset guard. Frontend build/Ruff/format/whitespace passed. |
| Browser rehearsal | Actual buttons completed start→pause→v2→real retrieval→approval→lost reply + worker exit 137→restart→VERIFIED. One receipt/one PATCH, new worker ID. Rehearsal archived and fresh NEW case prepared. |
| Team access | Three specified groupmates invited with Project Data Access Read/Write in organizer project. Driver credentials and per-machine IP access remain separate. |
| Retained development Atlas | SettleFlow2.0 / tradeops-sandbox remains retained; active .env targets organizer Cluster0. Do not delete it as demo cleanup. |

## 3. Invariants

- Public SEC observations are historical aggregate context only. Trades/accounts/instructions/receipts
  are fictional; never connect to a real financial authority. ACCEPTED is not final settlement.
- Deterministic read-only investigator; no generative LLM in this MVP. Actual Voyage/Atlas retrieval,
  never a fake search result. Memory suggests tools and cannot authorize a mutation.
- Only worker calls custodian PATCH, after exact-hash approval, live baseline/mapping/policy checks and
  acknowledged majority+j intent. Approval and Apply are separate controls.
- Stable operation and canonical payload survive every restart. Unknown outcome means verify first.
  Only authoritative 404 + unchanged approved inputs permits a budgeted same-key retry.
- Receipt and instruction must agree with saved intent on IDs/hash/account/revision/status and stable
  trade facts. ACK or read-only proof counters alone cannot close the Atlas case.
- Unknown schema/conflicting evidence→MANUAL_REVIEW; unavailable verification is never treated as absence.
- CaseStore updates guard caseId/runId/stage/version; reset archives old run and takes worker lease.
- Runtime uses PyMongo and readWrite user, setup uses dbAdmin-scoped URI. Only vector aggregation uses
  local read concern; cases/checkpoints retain majority reads and majority+j writes.
- Secrets only in ignored .env, mode 0600. No keys/URIs/tokens in logs, source, frontend or screenshots.
- Local demo token + HttpOnly SameSite cookie is not production SSO; no real transfers or settlement.
- Never drop databases/collections or delete retained clusters as part of reset/testing.

## 4. Running and verification

Repo root, separate terminals:

```bash
./scripts/dev.sh       # all HTTP services and frontend; keep running
./scripts/reset.sh     # stops tracked local worker, archives old synthetic run
./scripts/worker.sh    # independent process; restart here after deliberate exit 137
```

Sign in at http://localhost:3000 with root .env DEMO_REVIEWER_TOKEN value, without surrounding quotes.
Default fresh run uses Original format, account-check pause ON, and other demo flags OFF. Start
reconciliation, wait for the account-check pause, open Demo controls and select Updated format, then
close and Continue reconciliation. Approve correction, open Demo controls to delay confirmation and
interrupt after submission, close, Apply approved correction, wait for actual exit, restart the worker. Main demo must show VERIFIED with one receipt,
one PATCH and different saved/resumed worker IDs. See demo-script.md for presenter timings.

New machine: supply local credentials/IP access then
`./scripts/setup.sh /absolute/path/market_fail_observations.json`. Python3.12+ (3.13 verified), Node18+;
venv scripts are primary, uv optional. Use existing organizer Cluster0; no new paid cluster needed.

```bash
cd backend
.venv/bin/pytest -m 'not atlas' -q
RUN_ATLAS_TESTS=1 .venv/bin/pytest -m 'atlas and not workflow' -q
RUN_ATLAS_TESTS=1 RUN_WORKFLOW_TESTS=1 .venv/bin/pytest -q
.venv/bin/python scripts/verify_atlas.py --require-memory
.venv/bin/ruff check .
.venv/bin/ruff format --check .
```

Live workflow tests intentionally require both opt-in flags, use unique synthetic case/trade IDs and
worker keys, free ports, temporary SQLite files, exact cleanup. They never drop the database, change
canonical SI-2041 or delete public observations. Offline tests clear only temporary exported application
settings; atlas tests keep real credentials. Root .env loading must remain active in runtime.
Frontend production check: `cd frontend && npm run build`.

## 5. Remaining work and boundaries

The final local demo implementation is complete. Review/commit/push this branch when requested, rehearse
the three-minute flow and record the one-minute clip. No deployment/publication was requested.

Future production work is outside the demo: real identity provider, external custodian protocol and
security model, a fenced/distributed scheduler, operational observability and broader validation.
A generative planner can be added later behind read-only tools; it may never self-approve or bypass
policy. The real public dataset does not supply per-trade causes or final settlement proof.

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

- **2026-11-14 — Final ProofStep/TradeOps implementation (Codex).** Fetched latest main a159af1 and
  created feat/proofstep-tradeops-demo. Implemented real API/session reviewer controls, persisted
  deterministic investigation, exact approval/denial and separate Apply, majority+j intent, single leased
  worker and real exit 137 crash windows, canonical custodian payload/receipt hashes and full independent
  read-back recovery. Extended merged simulator/frontend contracts rather than replacing them. Imported
  all 66,693 SEC EJSON rows twice with no rejection/duplicates; visible TTE CUSIP/date context is explicitly
  separate from fictional 100-share trade. Added live v1→v2 pause, real Voyage/Atlas INC-004-guided contract
  read/adapter, mappingRevision guards, manual-review/no-action paths, safe reset/history and run scripts.
  All 66 tests passed (49 offline, 8 Atlas,9 real-process workflow); both real crash tests recovered with
  same operation and one receipt/one PATCH. Frontend build, Ruff/format/whitespace passed. Browser buttons
  reproduced adaptation→approval→lost reply→worker 71012 exit 137→worker 75102 VERIFIED, one receipt/one PATCH,
  rev 2/SAFE-401; archived rehearsal and reset fresh case. Updated CLAUDE.md, README and every docs file.
  Local app credentials generated in ignored .env without printing; no commit/push or paid provisioning.

- **2026-11-14 — Operational workflow redesign (Codex).** User requested an action-oriented financial
  workflow and nontechnical terminology. Defined Track3 problem in problem-statement.md, with precise
  distinctions from Track1/2. Rebuilt the frontend as one stage-driven case with four-step rail, exception
  document, reconciliation checklist, account-change approval and custodian confirmation receipt.
  Added business labels/errors, persistent trade context, collapsed source/audit evidence and native
  modal Demo controls. Kept all actual HTTP/version/hash/policy/checkpoint semantics; no backend changes.
  Updated CLAUDE.md, README and all docs. Validation and final rehearsal results recorded below.

  Validation: production TypeScript/Vite build passed; git whitespace check passed. Real redesigned UI
  rehearsal completed start→pause→Updated format→live retrieval→approval→delayed reply→exit 137→restart→
  Correction confirmed, with 1 recorded correction/1 submission. New worker used the saved operation.
  Verified 390px layout (pageWidth=viewportWidth=390), modal controls and Escape/focus return; restored
  normal viewport. Archived successful run and left a fresh NEW case with service running. Backend
  contracts unchanged; earlier 66-test suite evidence remains applicable, not presented as a new rerun.
  Redesign changes are uncommitted on feat/proofstep-tradeops-demo.

- **2026-11-14 — Multi-case workflow and verified learning (Codex).** Added four independent fictional
  instructions/trades and actionable queue. Follow-up becomes available after first VERIFIED+STORED,
  enforced by API as well as UI. Added scoped case controls/proof, multi-case worker scan, all-case reset
  archive and test fixture isolation. Verification atomically records a pending learning outbox; worker
  revalidates proof, embeds/upserts stable learned incident with source run/receipt/hash provenance.
  Actual scoped Atlas retrieval changes the next investigation to live-contract-first; no copied
  account or approval. Added provider backoff and query-vector cache after real Voyage 429 in repeated
  tests. Added visible independent directory reference and80-vs-800 conflict explanation. Browser
  NO_ACTION/manual-review paths passed. Automated two-case real retrieval test passed; 55 offline and 8
  Atlas foundation checks passed. Original 9 workflow regressions passed before final cache/backoff;
  final learning/availability rehearsal and validation are recorded below. Docs updated throughout.

- **2026-11-14 — Product framing correction (user).** TradeOps is the demonstrated financial software;
  ProofStep is the architecture/methodology implemented as its control layer to solve Track3. Updated
  primary UI/browser brand to TradeOps and kept ProofStep in secondary control evidence and docs.
  This steering is part of the ongoing multi-case/learning implementation, not a replacement task.

  Final validation: 55 offline tests and 8 Atlas foundation tests passed. The final real-process learning
  test passed in 40s, including verified publication, real scoped retrieval, authenticated publication
  retry without an extra correction, distinct follow-up approval/operation/receipt, and one submission
  per case. Earlier 9 workflow regressions also passed; the complete suite was not rerun as one batch
  after provider-backoff changes. Production TypeScript/Vite, Ruff/format and whitespace checks passed.
  Browser TradeOps SI-2041 reached VERIFIED+STORED; SI-2042 actually retrieved that incident (score 0.859),
  read live contract before its first account lookup, and is left AWAITING_APPROVAL with zero submissions.
  SI-2043 is NO_ACTION and SI-2044 MANUAL_REVIEW, each with zero submissions/corrections. Premature
  follow-up API start returned 409 EXPERIENCE_NOT_READY. Main brand/browser title TradeOps, ProofStep
  retained as secondary architecture/control-layer attribution. Final screen saved and left open;
  current services and worker running. All changes remain uncommitted on feat/proofstep-tradeops-demo.
