# HTTP contracts — implemented demo

All services bind to localhost. Business data and effects are synthetic; the SEC context collection is
public historical data. API errors use `{ "error": { "code": "...", "message": "..." } }`.
Browser calls `/api` through the Vite :3000 proxy to FastAPI :8000. API dates are ISO strings and Decimal128
prices are exact decimal strings. OpenAPI for each service is available at its `/docs`.

## 1. Reviewer authentication

`POST /api/auth/login` body `{ "token": "<local DEMO_REVIEWER_TOKEN>" }` validates the configured demo
secret and sets an HttpOnly, SameSite=strict cookie (`proofstep_reviewer`, path `/api`, max-age 8h).
`GET /api/auth/session` returns server-derived `{reviewerId,role,authMethod:"DEMO_TOKEN"}` after checking
current policy. CLI/test clients may instead send `X-Reviewer-Token`. Do not send identity/role in a body.
API restart clears in-memory sessions; sign in again. No production SSO is claimed.

All POST case/demo routes require reviewer auth. Mutation Origins, when present, must be
`http://localhost:3000` or `http://127.0.0.1:3000`. Read-only health/source/proof views are public local
demo views. Auth errors:401 REVIEWER_AUTH_FAILED;403 REVIEWER_NOT_CONFIGURED,
REVIEWER_NOT_AUTHORIZED, ORIGIN_NOT_ALLOWED. Demo controls also require DEMO_MODE=true.

## 2. Case API — port 8000

| Method / route | Body / response |
|---|---|
| GET `/api/health` | API/Atlas/simulator availability, real worker instance/PID/heartbeat/online and real memory status |
| GET `/api/cases` | Synthetic case documents |
| GET `/api/cases/{caseId}` | Full case without Mongo `_id`, worker status and compatibility aliases |
| GET `/api/cases/{caseId}/timeline` | `{events:[...]}` stored oldest-first (UI renders newest-first) |
| GET `/api/cases/{caseId}/sources` | Independent current broker/directory/custodian reads with `ok,fetchedAt,request,data`; per-source errors do not fabricate data |
| POST `/api/cases/{caseId}/start` | `{version:1}`; NEW→INVESTIGATING |
| POST `/api/cases/{caseId}/decision` | `{version:14,proposalHash:"sha256:...",decision:"APPROVE"}` or DENY |
| POST `/api/cases/{caseId}/execute` | `{version:15}`; APPROVED remains APPROVED, sets executionRequested; worker acts later |

Legacy `/investigate` aliases `/start`; `/approve` aliases `/decision` and defaults decision=APPROVE.
Do not hardcode example version numbers: every saved step/control increments the current version.
All transitions are guarded by stage, version and server-loaded runId.

Case fields include caseId/runId/tradeId/portfolioId/stage/version/evidence/events/marketContext,
investigation.steps/precedents/retrieval/phase, proposal/proposalHash, approval, executionRequested,
operation/checkpoint, verification and manualReview. API aliases: instructionId=caseId, demoRunId=runId,
intent=operation, timeline=events. Stored stages: NEW, INVESTIGATING, AWAITING_APPROVAL, APPROVED,
AWAITING_VERIFICATION, VERIFIED, DENIED, NO_ACTION, MANUAL_REVIEW.

Approval records server identity/role, approvedAt, decision, approvedProposalHash and policyVersion.
The proposal binds run/case/instruction/trade/portfolio, expectedRevision, old/new account,
mappingRevision, mutation and policyVersion. Denial is terminal and sends nothing. Execution request
also sends nothing directly: the worker performs pre-send checks, majority intent and eventual PATCH.

| Status | Code | Meaning |
|---|---|---|
| 404 | CASE_NOT_FOUND | Initialize/reset demo first |
| 409 | STAGE_CONFLICT | Wrong stage/version or duplicate action; refresh before retrying |
| 409 | PROPOSAL_HASH_MISMATCH | Submitted hash differs from current stored/recomputed proposal |
| 409 | POLICY_VERSION_MISMATCH | Proposal does not match current policy |
| 422 | FastAPI validation | Invalid type/body/decision |

## 3. Demo controls — authenticated, DEMO_MODE only

| Method / route | Body | Effect |
|---|---|---|
| POST `/api/demo/reset` | `{confirm:"RESET"}` | Acquires worker lease, resets 3 synthetic stores, archives prior case, creates NEW/new run; preserves market/policy/incidents |
| GET `/api/demo/state` | — | Custodian faults, directoryContractVersion and case demo flags |
| POST `/api/demo/faults` | Optional booleans below | Records case flags/event then updates custodian fault controls |
| POST `/api/demo/directory-version` | `{version:1}` (1, 2 or 3) | Changes live directory response contract |
| GET `/api/demo/custodian-proof` | — | Live custodian receipts/revisions/request counters for configured demo instruction |

Fault keys: lostResponse, operationsUnavailable, crashWorkerOnUnknown, pauseDirectoryRead,
crashBeforeSend. Omitted values stay unchanged. Setting pauseDirectoryRead=false also clears
directoryPaused so the persisted investigation can continue. The pause event happens immediately
before the worker's first directory account read. Directory shape changes preserve mappingRevision 7.

Reset:400 CONFIRMATION_REQUIRED if confirm is not RESET;409 WORKER_RUNNING while lease held;
409 RESET_CONFLICT if the active run changes;403 DEMO_MODE_DISABLED outside demo mode.
Reset is a local demonstration control, not production distributed rollback.

## 4. Broker simulator — port 8101

- GET `/health`: source SIMULATED_BROKER.
- GET `/trades/TR-2041`: tradeId,portfolioId,side,security/symbol,quantity,price,currency,status,executedAt,
  cusip,settlementDate,source. Canonical: BUY 100 TTE USD 91.20, EXECUTED, CUSIP F92124100,
  settlementDate2026-09-15.
- GET `/broker/trades/{trade_id}`: namespaced alias.
- POST `/admin/reset`: requires X-Sim-Admin; reloads fictional fixtures.

## 5. Directory simulator — port 8102

GET `/contract` (alias `/directory/contract`) returns version/contractVersion, accountPath, statusPath,
portfolioPath,changedAt,source. GET `/accounts/P-17` (alias `/directory/portfolios/P-17`) returns one of:

```json
{"portfolioId":"P-17","settlementAccount":"SAFE-401","accountStatus":"ACTIVE","retiredAccounts":["SAFE-100"],"mappingRevision":7}
```

```json
{"schemaVersion":2,"portfolio":{"id":"P-17"},"delivery":{"safekeepingAccount":"SAFE-401","status":"ACTIVE"},"mappingRevision":7}
```

v3 uses `routing.custodyLeg.acct` and portfolioRef and has no validated worker adapter. All versions also
include timestamps/source; v2 includes history. A directory with zero/multiple active authorized
accounts returns 409 AMBIGUOUS_ACTIVE_ACCOUNT rather than choosing one.

GET `/account-status/{accountId}` returns accountId,portfolioId,status,authorized,retiredOn,source.
POST `/admin/contract` body `{version:1|2|3}` and POST `/admin/reset` require X-Sim-Admin.

## 6. Custodian simulator — port 8103

GET `/instructions/SI-2041` returns instruction/trade/portfolio,side,security/symbol,quantity,cusip,
settlementDate,revision,safekeepingAccount,status,rejectionReason,latestOperationId,updatedAt,source.
Namespaced `/custodian/instructions/{instruction_id}` aliases GET/PATCH.

### PATCH `/instructions/SI-2041`

Header `Idempotency-Key: OP-...`; canonical body:

```json
{"expectedRevision":1,"accountId":"SAFE-401"}
```

Legacy `{expectedRevision,newAccount,operationId}` is accepted for compatibility; contradictory account
fields or header/body operation IDs are rejected. Canonical payloadHash is SHA-256 over the stable
`{instructionId,expectedRevision,accountId}`, independent of alias spelling. New operation updates
instruction + revision history + receipt in one SQLite transaction. Known key is checked before revision:
same key/hash returns original receipt; different hash returns 409 IDEMPOTENCY_KEY_REUSED. Missing key400;
stale new operation409 STALE_REVISION. Worker is the only application component permitted to call PATCH.

Receipt contains receiptId,operationId,instructionId,previousRevision,resultRevision,account,status,
committedAt,payloadHash,source; aliases accountId/revision/appliedAt are also supplied. A normal ACK
still requires a separate read-back before case verification.

### GET `/operations/{operation_id}`

Returns original receipt when found (also `/custodian/operations/{operation_id}`). Confirmed404 is the
only absence signal.503 OPERATIONS_UNAVAILABLE and timeouts are not absence and cannot authorize retry.

### GET `/admin/proof?instructionId=SI-2041`

Read-only actual SQLite evidence: instructionId,currentRevision,currentAccount,status,receiptCount,
patchRequestCount,receipts[],revisions[],patchRequests[]. It is independently fetched from Atlas case
state, so a committed instruction may show one receipt while the case remains AWAITING_VERIFICATION.
The frontend only labels "applied exactly once" once VERIFIED and receipt/operation match.

POST `/admin/faults` (X-Sim-Admin), optional `{lostResponse,operationsUnavailable}`; GET `/admin/faults`
reads them. Lost response is one-shot, consumed only on a committed amendment, and delays the reply
beyond the worker timeout **after** transaction commit. POST `/admin/reset` clears fictional instructions,
receipts, patch log and faults, then reloads fixtures. Normal UI uses guarded TradeOps reset instead.

## 7. Observable events

CASE_OPENED, INVESTIGATION_REQUESTED, TOOL_CALLED, MARKET_CONTEXT_READ, DIRECTORY_READ_PAUSED,
PRECEDENT_RETRIEVED/RETRIEVAL_PENDING, PROPOSAL_CREATED, APPROVED/DENIED, APPROVAL_INVALIDATED,
EXECUTION_REQUESTED, INTENT_PERSISTED, PATCH_SENT, ACK_RECEIVED/OUTCOME_UNKNOWN,
RESUMED_FROM_CHECKPOINT, RETRY_SAME_KEY, VERIFICATION_DEFERRED, VERIFIED, NO_ACTION, MANUAL_REVIEW,
FAULT_CONFIGURED. The deliberate hard crash saves neither ACK nor UNKNOWN; recovery relies on intent.
Tool details persist in investigation.steps including request, evidenceId, timing and actual guidedBy.

## 8. Frontend business labels

The operational redesign changes presentation only; HTTP routes, version/hash guards and worker authority
are preserved. Start reconciliation calls /start, Approve correction calls /decision(APPROVE), Decline
calls /decision(DENY), Apply approved correction calls /execute. Continue reconciliation clears the demo
pause. Demo controls uses Updated format for directory version2, confirmation delay for lostResponse,
and Interrupt processing after submission for crashWorkerOnUnknown. Diagnostics retain raw API evidence
only behind disclosures. Human-facing errors translate API codes without suppressing backend failures.

## 9. Multi-case contract extension

GET /api/cases lists only the configured demo scope in caseId order. Each case may include title,
scenarioKind,demoOwner,demoBatchId,learning and investigation.reusedExperience. GET detail and POST
start/decision/execute use the selected caseId; unrelated synthetic scopes return404. Similar follow-up
/start requires the first case VERIFIED + learning STORED, otherwise409 EXPERIENCE_NOT_READY.

GET /api/demo/state and /api/demo/custodian-proof accept optional caseId query parameter (default
configured canonical case). POST /api/demo/faults accepts optional caseId in the body. The worker-fault
flags are per-case; custodian/network and directory-format injections are simulator-wide presenter
controls. Present one scenario at a time. Reset archives all 4 default cases, with one scoped case in
isolated test configurations. Events add EXPERIENCE_CHECKED, EXPERIENCE_LOOKUP_PENDING,
EXPERIENCE_REUSED, EXPERIENCE_SAVED and EXPERIENCE_PENDING. Memory publication never grants approval.

Product framing: **TradeOps** is the financial application and the name shown in its interface.
**ProofStep** is the control-layer architecture/methodology implemented over the TradeOps workflow.
Present the TradeOps case lifecycle, then explain how the ProofStep layer provides durable intent,
policy/approval gates, recovery, verified completion and reusable verified experience for Track3.

A VERIFIED case whose learning publication exhausted3 attempts can POST
/api/cases/{caseId}/learning/retry with {version}. Reviewer auth and version guards apply; it resets
only the learning outbox, never executes the custodian operation again. Stored or still-processing
experience returns409. UI label: Retry saving experience.
