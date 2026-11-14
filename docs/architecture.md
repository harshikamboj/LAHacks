# TradeOps Reconciler — Architecture

> Hackathon: MongoDB *Agents in Context* Toronto · Track #3 **Finish the Job**.
> Primary spec: the team's *Master Build Brief* (summarised here) + `TradeOps_Reconciler_Blueprint.docx`.
> All data is **synthetic**. No real brokers, banks, custodians, accounts or production systems.

## 1. Product in one sentence

TradeOps Reconciler investigates a rejected securities settlement instruction, verifies the correct
receiving account across independent systems, obtains approval for a precise amendment, submits it,
and **proves it took effect exactly once — even when the custodian's reply is lost and the worker crashes.**

Scope is deliberately narrow: **one** pre-seeded rejected instruction, **one** mutation type
(amend the safekeeping account on that existing instruction). Final status is *accepted for processing*,
not settled. No cash or securities move.

## 2. Canonical seeded scenario (use these IDs everywhere)

| Source | Record |
|---|---|
| Broker | `TR-2041`: BUY **100 XYZ** @ **CAD 42.50**, portfolio `P-17`, status `EXECUTED` |
| Custodian | `SI-2041` → `TR-2041`; revision `1`, status `REJECTED`, safekeeping account `SAFE-100` |
| Directory | `SAFE-100` RETIRED; `SAFE-401` ACTIVE and authorized for `P-17` |
| Expected amendment | revision `2`, account `SAFE-401`, status `ACCEPTED` |
| Guarantee | exactly **one** custodian receipt / revision increment after a lost response + worker restart |

Fixtures live in `backend/fixtures/*.json`.

## 3. Decisions already made

| Topic | Decision |
|---|---|
| LLM | **None for the MVP.** The investigator is deterministic. Its next read-only step is guided by **Atlas Vector Search** over verified past incidents (each incident's `suggestedNextCheck` maps to a read-only tool). An LLM can be added later behind the same tool interface; it may never mutate, approve or bypass policy. |
| Embeddings | **Voyage AI** `voyage-3.5-lite`, 1024 dims, cosine, `VOYAGE_API_KEY`. Same model for indexing (`input_type=document`) and querying (`input_type=query`). If key or index is missing, retrieval reports `PENDING` with a reason — **never faked**. |
| Database | MongoDB **Atlas Sandbox** (organizer-provided), accessed at runtime **only via PyMongo** with the app's own credentials (`MONGODB_URI`). MCP is a setup tool, not a runtime dependency. Atlas setup happens in a teammate's session — see `docs/AI_CONTEXT.md`. |
| Backend | Python 3.12, `uv`, FastAPI, Pydantic v2, PyMongo, httpx, pytest. |
| Simulators | Three **separate FastAPI processes**, each with its **own SQLite file**. Independent authorities; survive worker restarts. |
| Worker | One separate Python process (`python -m app.worker`) running an explicit state machine. **The only component that calls `PATCH`.** Killable/restartable independently. No queues, no LangGraph. |
| Frontend | React + Vite + TypeScript, plain CSS. One **case workbench** screen. Polls the API every ~1 s. **No Streamlit, not a dashboard.** |
| Reviewer auth | Clearly labeled **demo reviewer token** (`X-Reviewer-Token` header vs `DEMO_REVIEWER_TOKEN` env). Not SSO and never presented as such. |
| Crash injection | Worker hard-exits itself (`os._exit(137)`) on an UNKNOWN outcome when the case's demo flag `crashWorkerOnUnknown` is set — a real process death after the custodian commit and before any outcome is saved. Restart via `scripts/worker.sh`. |

## 4. Processes and ports

```text
React Case Workbench (3000)  <--REST + 1s polling-->  FastAPI API (8000)
                                                         |  reads/writes cases, policies (PyMongo)
                                                         |  live READS of simulators for evidence cards
                                                         v
                                                  MongoDB Atlas Sandbox
                                                   cases · incidents(+vector index) · policies · workers
                                                         ^
                                                         |  stage scan, conditional updates, heartbeat
                                              Workflow Worker (python -m app.worker)
                                                         |
                        +--------------------------------+-------------------------------+
                        v                                v                               v
                Broker sim (8101)              Directory sim (8102)            Custodian sim (8103)
                broker.db (SQLite)             directory.db (SQLite)           custodian.db (SQLite)
                executed trade                 active account, /contract       instruction, receipts,
                                               V1/V2/unknown shapes            idempotency keys, faults
```

| Process | Port | Store | Owns |
|---|---|---|---|
| Broker sim | 8101 | `backend/simulators/data/broker.db` | executed trade (read-only) |
| Directory sim | 8102 | `backend/simulators/data/directory.db` | current safekeeping account, response contract version |
| Custodian sim | 8103 | `backend/simulators/data/custodian.db` | instruction, revisions, operations/receipts, idempotency, faults |
| API | 8000 | Atlas | case lifecycle, approval authorization, demo controls |
| Worker | — | Atlas | investigation, pre-send intent, PATCH, verification, recovery |
| Frontend | 3000 | — | workbench UI (Vite dev proxy `/api` → 8000) |

Trust boundary: the **API never calls custodian `PATCH`**. The API only records approval and an
`executionRequested` flag; the worker performs the mutation after re-checking policy and live evidence.

## 5. Repository layout

```text
LAHacks/
  README.md  CLAUDE.md  .env.example  .gitignore
  docs/ architecture.md  api-contracts.md  demo-script.md  AI_CONTEXT.md
  scripts/ dev.sh (3 sims + API)  worker.sh  kill-worker.sh  reset.sh
  backend/
    pyproject.toml
    app/
      main.py  config.py  models.py  db.py  hashing.py  worker.py
      routes/   cases.py  demo.py  health.py
      services/ investigation.py  approvals.py  workflow.py  verification.py
                memory.py  directory_adapters.py  simulator_clients.py
    simulators/ common.py  broker.py  directory.py  custodian.py  seed.py  data/ (gitignored)
    fixtures/   trades.json  instructions.json  accounts.json  incidents.json  policies.json
    scripts/    setup_atlas.py   # collections, validator, indexes, vector index, seed policies+incidents
    tests/      test_idempotency.py  test_approval_guards.py  test_directory_contract.py
                test_happy_path.py  test_crash_recovery.py  conftest.py
  frontend/
    package.json  vite.config.ts  index.html
    src/ main.tsx  App.tsx  lib/api.ts  styles.css
         components/ CaseHeader  SourceCards  InvestigationPanel  ApprovalCard
                     Timeline  FailureLab  ProofPanel
```

## 6. MongoDB design

### Collections

| Collection | Purpose |
|---|---|
| `cases` | one document per case: stage, version, evidence, proposal, approval, operation intent, checkpoint, verification, bounded events |
| `incidents` | 10 synthetic verified/unverified historical incidents + `embedding` (Vector Search) |
| `policies` | `settlement-amendment` policy `v1`: reviewers/roles, allowed mutation, retry budget, default directory contract |
| `workers` | heartbeat doc `{_id: "workflow-worker"}` so the UI can show worker online/offline |

### `cases` document

```jsonc
{
  "caseId": "SI-2041",              // unique
  "runId": "r7f3c2a1",              // regenerated on every demo reset; part of proposal hash
  "synthetic": true,                // reset only ever touches synthetic demo docs
  "tradeId": "TR-2041",
  "portfolioId": "P-17",
  "stage": "AWAITING_VERIFICATION", // enum, see §7
  "version": 7,                     // +1 on every conditional transition
  "evidence": {
    "broker":            { "tradeId": "TR-2041", "status": "EXECUTED", "security": "XYZ", "quantity": 100, "side": "BUY", "fetchedAt": ISODate },
    "custodianBaseline": { "instructionId": "SI-2041", "revision": 1, "account": "SAFE-100", "status": "REJECTED", "rejectionReason": "...", "fetchedAt": ISODate },
    "directory":         { "activeAccount": "SAFE-401", "baselineAccountStatus": "RETIRED", "contractVersion": 2, "adapter": "v2", "fetchedAt": ISODate }
  },
  "investigation": {
    "steps": [ { "n": 1, "tool": "get_custodian_instruction", "request": "GET /instructions/SI-2041", "ok": true, "summary": "...", "guidedBy": null, "at": ISODate, "ms": 12 } ],
    "precedents": [ { "query": "...", "status": "FOUND|PENDING|NONE", "incidentId": "INC-007", "score": 0.83, "suggestedNextCheck": "GET_DIRECTORY_CONTRACT", "reason": "..." } ],
    "diagnosis": "Instruction rejected because SAFE-100 is retired; directory reports SAFE-401 active for P-17."
  },
  "proposal": {
    "caseId": "SI-2041", "runId": "r7f3c2a1", "instructionId": "SI-2041", "tradeId": "TR-2041", "portfolioId": "P-17",
    "expectedRevision": 1, "oldAccount": "SAFE-100", "newAccount": "SAFE-401",
    "mutation": "AMEND_SAFEKEEPING_ACCOUNT", "policyVersion": "v1"
  },
  "proposalHash": "sha256:<hex>",   // sha256 of canonical JSON (sorted keys, no spaces) of `proposal`
  "approval": { "reviewerId": "demo-reviewer", "role": "SETTLEMENT_APPROVER", "approvedAt": ISODate,
                "approvedProposalHash": "sha256:<hex>", "policyVersion": "v1", "authMethod": "DEMO_TOKEN" },
  "executionRequested": true,
  "operation": {
    "operationId": "OP-SI-2041-<first 8 hex of proposalHash>",  // stable; never regenerated
    "idempotencyKey": "<same as operationId>",
    "payload": { "expectedRevision": 1, "newAccount": "SAFE-401", "operationId": "OP-SI-2041-..." },
    "attemptCount": 1, "maxAttempts": 3, "lastSentAt": ISODate, "lastOutcome": "UNKNOWN|ACK|REJECTED"
  },
  "checkpoint": { "stage": "AWAITING_VERIFICATION", "operationId": "OP-SI-2041-...", "savedAt": ISODate,
                  "savedByWorkerId": "worker-4812-ab12", "writeConcern": "majority" },
  "verification": { "deferrals": 0, "receiptId": "RCPT-...", "revision": 2, "account": "SAFE-401", "status": "ACCEPTED",
                    "verifiedAt": ISODate, "resumedByWorkerId": "worker-4907-cd34" },
  "manualReview": { "code": "UNKNOWN_DIRECTORY_CONTRACT", "detail": "..." },
  "demo": { "crashWorkerOnUnknown": false },
  "events": [ { "at": ISODate, "type": "INTENT_PERSISTED", "stage": "AWAITING_VERIFICATION", "actor": "worker:worker-4812-ab12", "detail": "...", "data": {} } ],
  "createdAt": ISODate, "updatedAt": ISODate
}
```

`events` is bounded: every push uses `{$push: {events: {$each: [evt], $slice: -100}}}`. Timestamps are
real BSON UTC datetimes (`datetime.now(timezone.utc)`).

### Conditional atomic transition (the only way stages change)

```python
cases.find_one_and_update(
    {"caseId": case_id, "stage": from_stage, "version": expected_version},
    {"$set": {"stage": to_stage, **fields, "updatedAt": now},
     "$inc": {"version": 1},
     "$push": {"events": {"$each": [event], "$slice": -100}}},
    return_document=ReturnDocument.AFTER,
)  # None  => stale or competing update => API returns 409 / worker skips
```

The **pre-send intent** write (APPROVED → AWAITING_VERIFICATION) uses
`cases.with_options(write_concern=WriteConcern("majority", j=True))`. Confirm the Sandbox tier supports it
(it is a replica set, so it should) and record the result in `AI_CONTEXT.md`.

### Indexes and validation (created by `backend/scripts/setup_atlas.py`, idempotent)

| Collection | Index |
|---|---|
| `cases` | `{caseId: 1}` unique |
| `cases` | `{"operation.operationId": 1}` unique, `partialFilterExpression: {"operation.operationId": {$exists: true}}` |
| `cases` | `{stage: 1}` (worker startup/resume scan) |
| `incidents` | `{incidentId: 1}` unique |
| `incidents` | Atlas Vector Search index `incident_vector_index` (below) |

`$jsonSchema` validator on `cases` (`validationLevel: "strict"`): required `caseId`, `tradeId`, `portfolioId`,
`stage`, `version`; `stage` enum; `caseId` pattern `^SI-[0-9]+$`; `operation.operationId` pattern `^OP-`.

Vector index definition (`type: "vectorSearch"`):

```json
{
  "fields": [
    { "type": "vector", "path": "embedding", "numDimensions": 1024, "similarity": "cosine" },
    { "type": "filter", "path": "source" },
    { "type": "filter", "path": "disposition" }
  ]
}
```

Query: `$vectorSearch {index: "incident_vector_index", path: "embedding", queryVector, numCandidates: 50, limit: 3, filter: {disposition: {$eq: "VERIFIED"}}}` then `$project` with `score: {$meta: "vectorSearchScore"}`, excluding `embedding`.

## 7. State machine

```text
NEW ──investigate──> INVESTIGATING ──(evidence consistent)──> AWAITING_APPROVAL ──approve──> APPROVED
                          │                                         ▲                          │ execute (flag)
                          │                                         │ approval invalidated     ▼
                          │                                         └──── (inputs changed) ── pre-send recheck
                          │                                                                    │ persist intent (majority)
                          ▼                                                                    ▼
                    MANUAL_REVIEW  <──── conflicts / unknown schema / budget exhausted ── AWAITING_VERIFICATION ──> VERIFIED
```

Allowed stages: `NEW, INVESTIGATING, AWAITING_APPROVAL, APPROVED, AWAITING_VERIFICATION, VERIFIED, MANUAL_REVIEW`.
Approval invalidation sends the case back to `INVESTIGATING` with `proposal`/`approval` cleared, so a fresh
proposal and a fresh approval are required.

### Who moves what

| Transition | Actor | Guard |
|---|---|---|
| NEW → INVESTIGATING | API `POST /investigate` | stage + version |
| INVESTIGATING → AWAITING_APPROVAL / MANUAL_REVIEW | worker | investigation result |
| AWAITING_APPROVAL → APPROVED | API `POST /approve` | demo reviewer token + role from `policies`, body `proposalHash` == recomputed hash == stored hash, policy version, stage + version |
| APPROVED (+`executionRequested`) | API `POST /execute` | stage + version |
| APPROVED → AWAITING_VERIFICATION | worker | live pre-send recheck passes; majority write of intent **before** PATCH |
| APPROVED → INVESTIGATING | worker | pre-send recheck found changed inputs (approval invalidated) |
| AWAITING_VERIFICATION → VERIFIED / MANUAL_REVIEW | worker | custodian read-back (§8) |

### Investigation (worker, read-only tools only)

1. `get_custodian_instruction` — `GET /instructions/SI-2041`. Status `ACCEPTED` → MANUAL_REVIEW `ALREADY_ACCEPTED` (zero writes). Not `REJECTED` → MANUAL_REVIEW.
2. `get_broker_trade` — `GET /trades/TR-2041`. Compare tradeId, portfolio, security, quantity, side; trade must be `EXECUTED`. Any mismatch → MANUAL_REVIEW `TRADE_MISMATCH`.
3. `retrieve_precedent` — Vector Search with the live rejection reason/note as query. Logged with incident ID + score, or `PENDING` + reason.
4. `get_account_status` — `GET /account-status/SAFE-100` must be `RETIRED` (otherwise the rejection is unexplained → MANUAL_REVIEW).
5. `get_directory_account` — `GET /accounts/P-17`, parsed with the last-known adapter (policy default `v1`).
   On parse failure: build a symptom string from the live response (missing path, observed keys) →
   `retrieve_precedent` → if the precedent's `suggestedNextCheck` is `GET_DIRECTORY_CONTRACT`, call it and log
   `guidedBy: INC-xxx`; if retrieval is pending, call it anyway under the deterministic fallback policy and log *why*.
6. `get_directory_contract` — `GET /contract`. Known version (1 or 2) → parse with that adapter. Unknown version,
   or parse still fails, or contract says the old version but parsing failed → MANUAL_REVIEW `UNKNOWN_DIRECTORY_CONTRACT`.
7. `get_account_status` — `GET /account-status/SAFE-401` cross-check: ACTIVE, authorized, portfolio `P-17`. Conflict → MANUAL_REVIEW `CONFLICTING_DIRECTORY_EVIDENCE`.
8. Build **one** proposal + `proposalHash` → AWAITING_APPROVAL.

Memory never overrides live data: the precedent only chooses *which read-only call to make next*.

## 8. Execution, ambiguous outcome and recovery (worker)

**Execute (stage APPROVED, `executionRequested: true`):**
1. Pre-send recheck: custodian still rev `expectedRevision`, `REJECTED`, `oldAccount`; directory still says `newAccount`
   (via `/contract` + adapter); `approval.approvedProposalHash == hash(proposal)`. If anything changed → invalidate.
2. Persist intent (majority): `operation{operationId, idempotencyKey, payload, attemptCount: 1}`, `checkpoint`,
   stage → `AWAITING_VERIFICATION`, event `INTENT_PERSISTED`.
3. `PATCH /instructions/SI-2041` with header `Idempotency-Key: <operationId>`, timeout `CUSTODIAN_TIMEOUT_SECONDS` (3 s).
   - 200 → event `ACK_RECEIVED`, then verify (an ACK alone is never trusted).
   - Timeout / connection reset → outcome **UNKNOWN**. If `demo.crashWorkerOnUnknown` → `os._exit(137)` **without writing anything**.
     Otherwise event `OUTCOME_UNKNOWN`; the next loop verifies.
   - 409 → event, then verify (verification decides).

**Verify (stage AWAITING_VERIFICATION — also the boot-resume path):**
On boot, the worker scans `stage in [APPROVED(executionRequested), AWAITING_VERIFICATION]` and appends
`RESUMED_FROM_CHECKPOINT` (with its new `workerId`) before continuing. It never re-investigates and never makes a new `operationId`.

| Custodian evidence (`GET /operations/{opId}` + `GET /instructions/SI-2041`) | Action |
|---|---|
| Receipt found and instruction agrees: `SI-2041`, `SAFE-401`, revision `expected+1`, `ACCEPTED`, `latestOperationId == opId` | → `VERIFIED`, save receipt + instruction evidence + `resumedByWorkerId` |
| 404 `confirmedAbsent` **and** instruction unchanged **and** approval hash still valid **and** `attemptCount < maxAttempts` | increment `attemptCount` (conditional), event `RETRY_SAME_KEY`, resend **identical payload with the same key** |
| 404 but instruction changed, or budget exhausted | → `MANUAL_REVIEW` |
| 503 / timeout | event `VERIFICATION_DEFERRED`, `verification.deferrals += 1`; stay pending; after 5 → `MANUAL_REVIEW` `VERIFICATION_UNAVAILABLE` |
| Receipt and instruction disagree | → `MANUAL_REVIEW` `CONFLICTING_CUSTODIAN_EVIDENCE` |

Atlas provides durable workflow memory; it does **not** by itself guarantee exactly-once in another database.
Exactly-once comes from (a) the stable `operationId` saved before sending, (b) the custodian's idempotency
contract, and (c) authoritative read-back verification.

## 9. Custodian idempotency contract

SQLite tables (`custodian.db`):

| Table | Columns |
|---|---|
| `instructions` | `instruction_id` PK, `trade_id`, `portfolio_id`, `security`, `quantity`, `side`, `revision`, `safekeeping_account`, `status`, `rejection_reason`, `rejection_note`, `latest_operation_id`, `updated_at` |
| `instruction_revisions` | (`instruction_id`, `revision`) PK, `safekeeping_account`, `status`, `operation_id`, `created_at` |
| `operations` | `idempotency_key` PK, `operation_id` UNIQUE, `receipt_id` UNIQUE, `instruction_id`, `payload_hash`, `payload_json`, `previous_revision`, `result_revision`, `account`, `status`, `created_at` |
| `patch_requests` | `id` PK autoinc, `instruction_id`, `idempotency_key`, `outcome`, `received_at` — **every** PATCH received, to prove no second PATCH |
| `faults` | `name` PK (`lost_response`, `operations_unavailable`), `armed` |

`PATCH /instructions/{id}` runs in **one `BEGIN IMMEDIATE` transaction**:
1. Look up `Idempotency-Key` **first**. Same payload hash → return the original receipt (`replayed: true`). Different hash → `409 IDEMPOTENCY_KEY_REUSED`.
2. Then check `expectedRevision == revision` and `status == REJECTED`; else `409 STALE_REVISION` / `409 NOT_AMENDABLE`.
3. Bump revision, set account, set status `ACCEPTED`, set `latest_operation_id`, insert revision row and receipt row. `COMMIT`.
4. **After commit**, if the one-shot `lost_response` fault is armed: disarm it and sleep `LOST_RESPONSE_DELAY_SECONDS` (default 10) before replying, so the caller times out even though the change is durable.

## 10. Demo-mode safety

- Demo routes (`/api/demo/*`) return 403 unless `DEMO_MODE=true`. Reset additionally requires body `{"confirm": "RESET"}`.
- Reset touches only the synthetic demo case (`synthetic: true`, `caseId` in the fixture list), the demo policy doc, and the simulators' own SQLite files.
- Simulator `/admin/*` routes require header `X-Sim-Admin: <SIM_ADMIN_TOKEN>`.
- No endpoint exposes arbitrary process control. Worker restart is a CLI step (`scripts/worker.sh`).
- Secrets only in `.env` (gitignored); `.env.example` has placeholders.

## 11. Excluded from MVP

Sharding, replication config, time-series collections, load balancing, Atlas Triggers, Change Streams,
queues/microservices, LangGraph, LLM (deferred), real SSO, final settlement / asset movement.
