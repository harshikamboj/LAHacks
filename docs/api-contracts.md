# API contracts

Implementation status (2026-11-14): these HTTP routes remain planned. The MongoDB integration exists in
`app/db.py`, `app/schema.py`, `app/seed.py`, and `app/services/memory.py`; see `mongodb-setup.md`.
API/worker services must reuse `CaseStore.cas_update` with expected runId/stage/version and handle None
as a 409 or a skipped competing worker action. `persist_intent` is called after live evidence checks and
must return before any PATCH. `IncidentMemory.retrieve` returns
`{query, status: FOUND|NONE|PENDING|DISABLED, reason, matches: [...]}`; real matches include incidentId,
score and suggestedNextCheck. Missing Voyage key produces PENDING, never a fabricated match.
Live backend retrieval is now verified with the saved key: the directory-field query returns INC-004
first and GET_DIRECTORY_CONTRACT as its suggestion. These HTTP routes remain to be implemented.

All JSON. Timestamps ISO-8601 UTC (`2026-11-14T15:04:05.123Z`). Errors use one shape everywhere:

```json
{ "error": { "code": "STALE_REVISION", "message": "human readable", "details": {} } }
```

IDs: trade `TR-2041`, instruction/case `SI-2041`, portfolio `P-17`, accounts `SAFE-100` / `SAFE-401`,
operation `OP-SI-2041-<8 hex>`, receipt `RCPT-<8 hex>`, incident `INC-001`…`INC-010`, worker `worker-<pid>-<4 hex>`.

---

All three simulators also expose `GET /health` → `{ "ok": true, "source": "SIMULATED_..." }`, are started with
`uvicorn simulators.<name>:create_app --factory`, and seed themselves from `backend/fixtures/` on first start.

## 1. Broker simulator — port 8101 (read-only authority for the executed trade)

### `GET /trades/{tradeId}`
200
```json
{ "tradeId": "TR-2041", "portfolioId": "P-17", "side": "BUY", "security": "XYZ",
  "quantity": 100, "price": "42.50", "currency": "CAD", "status": "EXECUTED",
  "executedAt": "2026-11-13T19:42:10Z", "source": "SIMULATED_BROKER" }
```
404 `TRADE_NOT_FOUND`.

### `POST /admin/reset` (header `X-Sim-Admin`)
Re-seeds `broker.db` from `backend/fixtures/trades.json`. 200 `{ "reset": true }`.

---

## 2. Account Directory simulator — port 8102 (authority for the current receiving account)

### `GET /accounts/{portfolioId}` — shape depends on the active contract version

**Contract v1**
```json
{ "portfolioId": "P-17", "settlementAccount": "SAFE-401", "accountStatus": "ACTIVE",
  "retiredAccounts": ["SAFE-100"], "asOf": "...", "source": "SIMULATED_DIRECTORY" }
```

**Contract v2** (account field moved)
```json
{ "schemaVersion": 2, "portfolio": { "id": "P-17" },
  "delivery": { "safekeepingAccount": "SAFE-401", "status": "ACTIVE" },
  "history": [ { "account": "SAFE-100", "status": "RETIRED", "retiredOn": "2026-10-31" } ],
  "asOf": "...", "source": "SIMULATED_DIRECTORY" }
```

**Contract v3 — "unknown" (no validated adapter; must route to MANUAL_REVIEW)**
```json
{ "schemaVersion": 3, "portfolioRef": "P-17",
  "routing": { "custodyLeg": { "acct": "SAFE-401" } }, "asOf": "...", "source": "SIMULATED_DIRECTORY" }
```
404 `PORTFOLIO_NOT_FOUND`. 409 `AMBIGUOUS_ACTIVE_ACCOUNT` (details `activeAccounts`) if the portfolio has ≠ 1 active
authorized account — the directory never picks one for you; treat as conflicting evidence → MANUAL_REVIEW.

### `GET /contract`
```json
{ "version": 2, "accountPath": "delivery.safekeepingAccount", "statusPath": "delivery.status",
  "portfolioPath": "portfolio.id", "changedAt": "...", "source": "SIMULATED_DIRECTORY" }
```
(v1: `settlementAccount` / `accountStatus` / `portfolioId`; v3: `routing.custodyLeg.acct` / null / `portfolioRef`.)

### `GET /account-status/{accountId}` — shape-independent cross-check
```json
{ "accountId": "SAFE-100", "portfolioId": "P-17", "status": "RETIRED", "authorized": false, "retiredOn": "2026-10-31" }
```

### `POST /admin/contract` (header `X-Sim-Admin`) body `{ "version": 1 | 2 | 3 }` → 200 `{ "version": 2 }`
### `POST /admin/reset` (header `X-Sim-Admin`) → contract back to v1, accounts re-seeded.

---

## 3. Custodian simulator — port 8103 (authority for instruction, amendment outcome and receipt)

### `GET /instructions/{instructionId}`
```json
{ "instructionId": "SI-2041", "tradeId": "TR-2041", "portfolioId": "P-17", "side": "BUY",
  "security": "XYZ", "quantity": 100, "revision": 1, "safekeepingAccount": "SAFE-100",
  "status": "REJECTED", "rejectionReason": "INVALID_SAFEKEEPING_ACCOUNT",
  "rejectionNote": "Receiving safekeeping account SAFE-100 is not open for delivery ...",
  "latestOperationId": null, "updatedAt": "...", "source": "SIMULATED_CUSTODIAN" }
```

### `PATCH /instructions/{instructionId}`
Header **`Idempotency-Key: OP-SI-2041-…`** (required, must equal body `operationId`).
```json
{ "expectedRevision": 1, "newAccount": "SAFE-401", "operationId": "OP-SI-2041-3fa9c1d2" }
```
Payload hash = sha256 of canonical JSON of `{instructionId, expectedRevision, newAccount, operationId}`.

200 (first time, or replay of same key + same payload)
```json
{ "receiptId": "RCPT-8c1e2f40", "operationId": "OP-SI-2041-3fa9c1d2", "instructionId": "SI-2041",
  "previousRevision": 1, "resultRevision": 2, "account": "SAFE-401", "status": "ACCEPTED",
  "committedAt": "...", "replayed": false }
```
| Status | code | When |
|---|---|---|
| 400 | `MISSING_IDEMPOTENCY_KEY` / `KEY_OPERATION_MISMATCH` / `INVALID_ACCOUNT` | header missing, header ≠ body `operationId`, account not `SAFE-<digits>` |
| 404 | `INSTRUCTION_NOT_FOUND` | |
| 409 | `IDEMPOTENCY_KEY_REUSED` | known key, different payload (checked **before** revision) |
| 409 | `STALE_REVISION` | `expectedRevision` ≠ current revision (unknown key) |
| 409 | `NOT_AMENDABLE` | instruction not `REJECTED` (unknown key) |

Fault `lost_response` armed: commit happens, then the reply is delayed `LOST_RESPONSE_DELAY_SECONDS` (one-shot).

### `GET /operations/{operationId}`
200 → the receipt (same shape as PATCH 200, `replayed` omitted).
404 → authoritative absence (no such operation was committed):
```json
{ "error": { "code": "OPERATION_NOT_FOUND", "message": "...",
             "details": { "operationId": "OP-...", "confirmedAbsent": true } } }
```
503 `OPERATIONS_UNAVAILABLE` when the `operations_unavailable` fault is armed (temporary; **not** absence —
its `details` never contains `confirmedAbsent`). `CustodianClient.lookup_operation()` returns `None` only for the 404 above.

### `GET /admin/proof?instructionId=SI-2041` (no auth; read-only)
```json
{ "instructionId": "SI-2041", "currentRevision": 2, "currentAccount": "SAFE-401", "status": "ACCEPTED",
  "receiptCount": 1, "patchRequestCount": 1,
  "receipts": [ { "receiptId": "RCPT-...", "operationId": "OP-...", "resultRevision": 2, "committedAt": "..." } ],
  "revisions": [ { "revision": 1, "account": "SAFE-100", "status": "REJECTED" },
                 { "revision": 2, "account": "SAFE-401", "status": "ACCEPTED", "operationId": "OP-..." } ],
  "patchRequests": [ { "idempotencyKey": "OP-...", "outcome": "COMMITTED_RESPONSE_DROPPED", "receivedAt": "..." } ] }
```

### `POST /admin/faults` (header `X-Sim-Admin`) body `{ "lostResponse": true, "operationsUnavailable": false }`
### `GET /admin/faults` → `{ "lostResponse": false, "operationsUnavailable": false }`
### `POST /admin/reset` (header `X-Sim-Admin`) → re-seed instruction rev 1 / REJECTED / SAFE-100, clear operations, patch log and faults.

---

## 4. TradeOps API — port 8000, prefix `/api`

### `GET /api/health`
```json
{ "api": "ok", "atlas": { "ok": true, "db": "tradeops", "error": null },
  "simulators": { "broker": "ok", "directory": "ok", "custodian": "ok" },
  "worker": { "online": true, "workerId": "worker-4812-ab12", "pid": 4812, "heartbeatAt": "...", "ageSeconds": 0.6 },
  "memory": { "vectorSearch": "READY|PENDING|DISABLED", "reason": null }, "demoMode": true }
```

### `GET /api/cases` → `[ { "caseId", "tradeId", "portfolioId", "stage", "version", "updatedAt" } ]`
### `GET /api/cases/{caseId}` → full case document (§6 of architecture.md), `_id` removed, dates ISO.
### `GET /api/cases/{caseId}/timeline` → `{ "events": [...] }` oldest first.

### `GET /api/cases/{caseId}/sources` — live reads for the three evidence cards
```json
{ "broker":    { "ok": true, "fetchedAt": "...", "request": "GET /trades/TR-2041", "data": { ... } },
  "directory": { "ok": true, "fetchedAt": "...", "request": "GET /accounts/P-17", "data": { ... }, "contract": { ... } },
  "custodian": { "ok": true, "fetchedAt": "...", "request": "GET /instructions/SI-2041", "data": { ... } } }
```
A source that is down returns `{ "ok": false, "error": "..." }` for that card only.

### `POST /api/cases/{caseId}/investigate` body `{ "version": 1 }`
NEW → INVESTIGATING. 200 case. 409 `STAGE_CONFLICT` if stage/version don't match.

### `POST /api/cases/{caseId}/approve`
Header `X-Reviewer-Token: <DEMO_REVIEWER_TOKEN>`; body `{ "proposalHash": "sha256:...", "version": 4 }`.
| Status | code |
|---|---|
| 200 | case now `APPROVED` |
| 401 | `REVIEWER_AUTH_FAILED` (missing/wrong token) |
| 403 | `REVIEWER_NOT_AUTHORIZED` (reviewer lacks `SETTLEMENT_APPROVER` in policy) |
| 409 | `PROPOSAL_HASH_MISMATCH` (body hash ≠ recomputed hash of stored proposal) |
| 409 | `STAGE_CONFLICT` (not AWAITING_APPROVAL or stale version — e.g. double click) |
| 409 | `POLICY_VERSION_MISMATCH` |

### `POST /api/cases/{caseId}/execute` body `{ "version": 5 }`
Sets `executionRequested: true` on an `APPROVED` case (event `EXECUTION_REQUESTED`). The **worker** performs the PATCH.
409 `STAGE_CONFLICT` otherwise. The API never calls the custodian PATCH.

### Demo controls — 403 `DEMO_MODE_DISABLED` unless `DEMO_MODE=true`

| Method | Route | Body | Effect |
|---|---|---|---|
| `POST` | `/api/demo/reset` | `{ "confirm": "RESET" }` | reset 3 simulators + recreate synthetic case `SI-2041` (stage NEW, new `runId`) + upsert policy `v1` |
| `GET` | `/api/demo/state` | — | `{ "faults": {...}, "directoryContractVersion": 1, "crashWorkerOnUnknown": false }` |
| `POST` | `/api/demo/faults` | `{ "lostResponse"?: bool, "crashWorkerOnUnknown"?: bool, "operationsUnavailable"?: bool }` (omitted = unchanged) | arms custodian faults (via admin API) and sets `case.demo.crashWorkerOnUnknown`; appends a `FAULT_CONFIGURED` event. *Until the case engine exists, `crashWorkerOnUnknown` returns `{applied: false, reason}`.* |
| `POST` | `/api/demo/directory-version` | `{ "version": 1 \| 2 \| 3 }` | switches directory contract |
| `GET` | `/api/demo/custodian-proof` | — | proxies custodian `/admin/proof?instructionId=SI-2041` |

---

## 5. Event types (case `events[].type`)

`CASE_OPENED, INVESTIGATION_REQUESTED, TOOL_CALLED, PRECEDENT_RETRIEVED, RETRIEVAL_PENDING, ADAPTER_SELECTED,
PROPOSAL_CREATED, APPROVED, APPROVAL_INVALIDATED, EXECUTION_REQUESTED, PRESEND_RECHECK_PASSED, INTENT_PERSISTED,
PATCH_SENT, ACK_RECEIVED, OUTCOME_UNKNOWN, RESUMED_FROM_CHECKPOINT, OPERATION_FOUND, OPERATION_ABSENT,
RETRY_SAME_KEY, VERIFICATION_DEFERRED, VERIFIED, MANUAL_REVIEW, FAULT_CONFIGURED`

Investigation tool steps are stored in `investigation.steps` (not as individual events) to keep `events` small.
