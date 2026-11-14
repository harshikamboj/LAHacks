# MongoDB setup and integration handoff

## Deployed environment (2026-11-14)

| Resource | Verified state |
|---|---|
| Organization | Agents in Context Toronto, `69ef9daf03d2ce35c2657862` |
| Project | Organizer Sandbox, `6af899b4fb07f6aa867aa481` |
| Cluster | Existing Cluster0, M10, AWS US_WEST_1, MongoDB9.0.7 |
| Database | `tradeops` |
| Vector index | `incidents.incident_vector_index`, READY/queryable; 9 real verified-incident vectors |
| Collections | `cases`, `case_runs`, `incidents`, `policies`, `workers`, `market_fail_observations`; empty `healthcheck` used for connectivity verification |
| Public dataset | 66,693 supplied SEC observations, full import and idempotent re-import verified |
| Runtime user | `tradeops-app`: readWrite only on tradeops, scoped to Cluster0 |
| Setup user | `tradeops-setup`: readWrite + dbAdmin only on tradeops, scoped to Cluster0 |
| Network | Development Mac's allowed public IP; no allow-all entry created |
| Secrets | Gitignored root `.env`, mode 0600; real local Atlas/Voyage and generated demo tokens |
| Team | Three user-requested groupmates invited with Project Data Access Read/Write |

The organizer identity matches the accepted Agents in Context Toronto invitation. The earlier free
SettleFlow2.0 / tradeops-sandbox development environment is retained, not used by active runtime. No
additional paid cluster was created. Development backup URIs remain only in local .env variables.
Project membership does not create personal database passwords or authorize each teammate's IP.

## Setup and credentials

Python3.12+ (3.13 verified), Node18+ and an allowed source IP are required. On a new machine copy
`.env.example` to root `.env`; supply scoped runtime/setup URIs and a Voyage key. On this Mac preserve
the already configured file. Never print credentials, publish the file or put keys in frontend code.

```bash
./scripts/setup.sh /absolute/path/market_fail_observations.json
```

The script installs backend/frontend dependencies, generates blank/placeholder SIM_ADMIN_TOKEN and
DEMO_REVIEWER_TOKEN locally, saves the supplied file path, installs schema/indexes/seeds, reuses valid
embeddings, and imports observations. It does not reset active case state. Runtime and verification use
MONGODB_URI; schema setup uses MONGODB_SETUP_URI. Both were verified against organizer Cluster0.

Individual commands from repo root:

```bash
backend/.venv/bin/python backend/scripts/configure_demo.py --market-file /absolute/path/market_fail_observations.json
backend/.venv/bin/python backend/scripts/setup_atlas.py
backend/.venv/bin/python backend/scripts/import_market.py /absolute/path/market_fail_observations.json
backend/.venv/bin/python backend/scripts/verify_atlas.py --require-memory
```

If changing Wi-Fi/machines prevents connection, add that machine's public IP in Atlas Network Access.
Each teammate keeps their own ignored `.env`; project invitations alone do not provide a driver login.
Do not delete retained clusters or broader organization resources as part of demo reset.

## Collection behavior

- `cases`: strict synthetic-case validation, unique caseId, unique partial operation.operationId, stage
  recovery index. Atomic comparison uses case/run/stage/version; events bounded to 100 and stored UTC.
- `case_runs`: archive on reset, unique (caseId,runId), retaining completed rehearsal history.
- `workers`: real heartbeat + five-second lease, preventing two workers/reset sharing the same case.
- `policies`: current enabled policy, version, permitted portfolio/mutation and authorized reviewer role.
  Setup/reset preserve current policy rather than silently replacing it.
- `incidents`: unique incidentId and actual 1024-dimension Voyage embeddings on the 9 VERIFIED examples.
- `market_fail_observations`: stable `_id` CUSIP:date, BSON settlement_date, Decimal128 prior_close_price
  or null, numeric outstanding_fail_quantity, source archive and descriptive labels. Compound
  `{cusip:1,settlement_date:1}` index supports contextual joins.

`CaseStore.persist_intent` majority+j writes the original operation/idempotency key, approved payload,
wire request, payloadHash, stage AWAITING_VERIFICATION and saved-by worker before dispatch. The actual
worker performs live rechecks first and stops sending if the write fails. A restart loads this stage
and intent directly, without reconstructing state by replaying the timeline. Application verification
then checks both independent custodian reads; database durability alone is not proof of external effect.

Reset requires the worker stopped, archives active case and rotates runId. It resets only fictional
simulator data and case execution state. It never deletes market observations, policy or incident memory.
`scripts/reset.sh` stops only the tracked local worker, then calls the authenticated guarded API reset.

## SEC dataset import and Atlas interaction

The supplied 19.9 MB file is newline-delimited MongoDB Extended JSON, not a single JSON array. All 66,693
rows parsed and stored; re-import retained 66,693 (zero duplicates). Dataset quality: 13,397 CUSIPs,
12 dates September 15–30, 2026,383 null prices and one blank symbol; zero malformed or duplicate-ID rows.
The full file previously matched the official `cnsfails202609b.zip` archive by record key and fields.
Source: [SEC fails-to-deliver data](https://www.sec.gov/data-research/sec-markets-data/fails-deliver-data).

Import uses BSON EJSON decoding, validates IDs/date/CUSIP/quantities/decimals, and batched 1,000 ReplaceOne
upserts by `_id`. It reports errors and verifies the exact demo anchor. The large file remains external
to Git, referenced by local MARKET_DATA_FILE. Missing values stay missing; the UI does not compute a
notional amount or treat aggregate failures as this trade's quantity.

In Atlas Data Explorer select Cluster0 → tradeops → market_fail_observations, filter:

```json
{"_id":"F92124100:2026-09-15"}
```

Expected: symbol TTE, CUSIP F92124100, UTC settlement_date 2026-09-15, outstanding_fail_quantity 1277,
Decimal128 prior_close_price 91.14. The actual worker lookup includes matching CUSIP and date too:

```javascript
db.market_fail_observations.findOne({
  _id: 'F92124100:2026-09-15',
  cusip: 'F92124100',
  settlement_date: ISODate('2026-09-15T00:00:00Z')
})
db.market_fail_observations.countDocuments({}) // 66693
db.cases.findOne({caseId: 'SI-2041'})
db.case_runs.find({caseId: 'SI-2041'}).sort({updatedAt: -1})
```

These are read-only examples for mongosh/Data Explorer as supported. The worker attaches a snapshot as
case.marketContext after cross-source identity checks; frontend reads it via the case API. Historical
SEC observations remain unchanged by the synthetic amendment. The dataset provides market context,
not a real instruction feed, account directory, root-cause label or evidence that a trade settled.

## Real Voyage / Atlas Vector Search

Voyage model `voyage-3.5-lite`, 1024 dimensions, document input for indexing and query input for live
retrieval. Embedding endpoint is `https://api.voyageai.com/v1/embeddings`. Obtain a key from
[Voyage API keys](https://dashboard.voyageai.com/api-keys), save VOYAGE_API_KEY in root .env;
VOYAGE_MODEL=voyage-3.5-lite and MEMORY_ENABLED=true. Existing local key is already verified. Do not use
an Atlas Model API key with the Voyage provider endpoint without implementing that separate provider.

Index `incident_vector_index` uses cosine on embedding; filters source,disposition,embeddingModel,
synthetic. `IncidentMemory.retrieve` returns actual top 3 IDs/scores/resolutions/allowlisted suggestions,
filtered to VERIFIED synthetic incidents and the configured model. INC-010 is unverified/unembedded.
Existing correct vectors are reused; changed incident text invalidates stale vectors.

The live mismatch query in the browser rehearsal returned **INC-004 (~0.85)** and its
GET_DIRECTORY_CONTRACT suggestion. The next recorded tool read the live contract with guidedBy=INC-004;
v2 re-read selected SAFE-401 only after account authorization validation. The standalone strict query
"directory payload moved the account field" also returns INC-004 first (~0.80).

Only `$vectorSearch` overrides read concern to local (Atlas requirement). Case/checkpoint operations
retain majority reads and majority+j writes. Missing credentials/index/embeddings/service availability
produce explicit PENDING; MEMORY_ENABLED=false gives DISABLED. No fake/local similarity fallback.

## Verification evidence

```bash
cd backend
.venv/bin/pytest -m 'not atlas' -q
RUN_ATLAS_TESTS=1 .venv/bin/pytest -m 'atlas and not workflow' -q
RUN_ATLAS_TESTS=1 RUN_WORKFLOW_TESTS=1 .venv/bin/pytest -q
.venv/bin/ruff check .
.venv/bin/ruff format --check .
```

**66 tests passed**: 49 offline, 8 Atlas foundation, 9 live workflow. Real workflow tests start separate
API/simulator/worker processes with unique synthetic case IDs/ports and temporary SQLite files. They
prove exit 137 after committed lost reply and after checkpoint-before-send; each recovers with the
original operation to one receipt/one PATCH. Guards cover stale/denied/wrong-hash approval, changed
mapping, unknown schema, mismatched trade, no-action, unavailable reads/no-blind-retry and reset refusal.
Live v1→v2 test consumes real Voyage/Atlas retrieval. Tests clean up only exact test records; no database
or canonical case is dropped. Offline tests isolate temporary exported settings; atlas tests keep real
credentials. Runtime .env loading is unchanged.

Browser rehearsal independently completed the main path: old worker 71012 → real exit 137; new worker 75102
→ read-back VERIFIED; 1 receipt, 1 PATCH, revision 2, SAFE-401. The rehearsal is archived when reset for a clean
new run. Frontend production build and backend static checks also pass.

Guarantee boundary: Atlas provides durable intent and state guards. The independent custodian simulator
provides transactional idempotency and authoritative receipts. Both are required for the demonstrated
exactly-once business effect; ACCEPTED is not final securities settlement.
