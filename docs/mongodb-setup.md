# MongoDB setup and integration handoff

## What is deployed (2026-11-14)

| Resource | Verified state |
|---|---|
| Organization | **Agents in Context Toronto**, `69ef9daf03d2ce35c2657862` |
| Project | Organizer Sandbox Project, `6af899b4fb07f6aa867aa481` |
| Cluster | Existing organizer `Cluster0`, M10, AWS `US_WEST_1`, MongoDB `9.0.7`, IDLE; database verification passed |
| Database | `tradeops` |
| Vector index | `incidents.incident_vector_index`, READY/queryable; 9 real verified-incident embeddings, strict semantic query passed |
| Collections | `cases`, `incidents`, `policies`, `workers`; verification also creates an empty `healthcheck` collection |
| Seed records | Case `SI-2041` / `TR-2041` / `P-17`, stage NEW; policy `settlement-amendment` v1; incidents INC-001 through INC-010 |
| Runtime access | `tradeops-app`: readWrite on tradeops only, scoped to this cluster |
| Setup access | `tradeops-setup`: readWrite + dbAdmin on tradeops only, scoped to this cluster |
| Network access | Development Mac's current public IP only; no allow-all network entry |
| Secrets | Local repository `.env`, gitignored, mode 0600; generated Atlas passwords were not committed |
| Organizer Sandbox | **Confirmed**: project belongs to Agents in Context Toronto, matching the accepted organizer invitation |
| Team project access | Three groupmates added with Project Data Access Read/Write; verified in Atlas Project Identity & Access |

Project membership grants access through Atlas. It does not provision personal database login credentials
or add each teammate's machine to the IP access list. Direct PyMongo connections still require database
credentials and an allowed source IP. The existing app/setup database users were not changed by the invites.

The user located the accepted organizer invitation and the correct Sandbox project during setup.
MCP now confirms the organization and project; the existing M10 Cluster0 is being reused. No extra paid
cluster was provisioned. Fresh, separate runtime/setup users and the current Mac IP entry were created
there through the connector, bypassing Quickstart's default Atlas Admin user.

Earlier setup was verified in the separately authorized SettleFlow 2.0 / tradeops-sandbox development
cluster (Free/M0, AWS US_EAST_1, MongoDB 8.0.37). Its synthetic data and resources are retained. The same
reproducible schema and seeds are now installed in the organizer Sandbox; the active local `.env`
connection targets Cluster0. Previous development URIs are retained only as local .env backup variables
MONGODB_DEVELOPMENT_URI and MONGODB_DEVELOPMENT_SETUP_URI.

Local `.env` recheck: both runtime and setup connections succeeded against organizer Cluster0/tradeops.
MONGODB_TIMEOUT_MS=10000 and MONGODB_VECTOR_INDEX=incident_vector_index are explicit in the local file.
Voyage key loads successfully and has been tested with real document/query embedding calls;
simulator admin/reviewer tokens remain example placeholders for future application setup. No local simulator health endpoint or worker heartbeat is active yet.

## Implemented database behavior

`app/config.py` loads the root `.env` from any working directory and represents credentials as secret
values. `app/db.py` connects with PyMongo, majority case reads and majority+journaled writes, with bounded
timeouts. The incident $vectorSearch aggregation overrides read concern to local, which Atlas requires;
this does not change case or checkpoint durability. Runtime never calls the Atlas MCP connector.

`CaseStore.create_case` uses insert-only initialization. Re-running setup preserves the case's run ID,
stage, approval and operation checkpoint. `cas_update` matches caseId + synthetic + runId + expected stage
+ version, then changes fields, increments version and appends one event atomically. A competing/stale
action returns None. The timeline keeps the latest 100 events; stored timestamps are UTC BSON dates.

`persist_intent` validates the typed proposal, scope, canonical SHA-256 approval hash, policy version,
reviewer role and execution request. It saves a stable operation ID, identical idempotency key, exact
payload and checkpoint together in AWAITING_VERIFICATION with majority+j acknowledgement. It refuses
to replace an existing operation. **The actual worker must first recheck live custodian and directory
evidence, send only after this call succeeds, and stop sending if the DB write throws or returns None.**
`list_resumable` reads APPROVED and AWAITING_VERIFICATION cases; `copy_operation` loads the existing intent.
`heartbeat` supports the future worker's liveness document; no fake online heartbeat is seeded.

`app/schema.py` installs a strict cases `$jsonSchema` validator: required IDs/run/stage/version/timestamps,
synthetic-only cases, stage enum, ID patterns, bounded events and operation payload types. It creates:

- `cases.caseId` unique (`case_id_unique`).
- `cases.operation.operationId` unique with an exists partial filter (`operation_id_unique`).
- `cases.stage` (`case_stage`) for recovery scans.
- `incidents.incidentId` unique (`incident_id_unique`).
- `policies.policyId` unique (`policy_id_unique`).

Setup never drops collections, resets cases, replaces policies, or changes an existing vector index with
a different definition. Fixture updates apply only to synthetic incident IDs; stale embeddings are
removed when their text/model metadata changes. A conflicting non-synthetic record causes a unique-key
error rather than being overwritten.

## Voyage and Vector Search

Verified live query: “directory payload moved the account field” returned **INC-004** first (score
0.799821), then INC-008 and INC-005. The first match suggests GET_DIRECTORY_CONTRACT; this is a read-only
suggestion, and the live directory/worker integration is still to build. All 9 VERIFIED incidents have
real embeddings; INC-010 remains excluded. The strict `--require-memory` check passed.

The READY/queryable `incident_vector_index` indexes `embedding` as 1024 dimensions with cosine similarity. Filter fields
are source, disposition, embeddingModel and synthetic. It is a real Atlas Vector Search index; its
existence/readiness is separate from having embeddings or proving semantic retrieval.

Use [Voyage's dashboard](https://dashboard.voyageai.com/) → API keys → **Create new secret key**.
Sign in or create your own account. Save the key directly in the gitignored root `.env`:

```dotenv
VOYAGE_API_KEY=<your-secret-key>
VOYAGE_MODEL=voyage-3.5-lite
MEMORY_ENABLED=true
```

Do not paste the key into chat, terminal output, docs or source control. This implementation uses
Voyage's `https://api.voyageai.com/v1/embeddings` endpoint. Atlas Model API keys use their own provider
endpoint; do not substitute a different provider's key here without implementing that provider.
See [Voyage key setup](https://docs.voyageai.com/docs/api-key-and-installation) and
[embedding model/input types](https://docs.voyageai.com/docs/embeddings).

Setup embeds only the 9 VERIFIED incidents using `symptom + " " + verifiedResolution`,
`voyage-3.5-lite`, document input type and 1024 dimensions. INC-010 is deliberately unverified and receives
no embedding. Valid unchanged embeddings are reused on subsequent setup runs.

`IncidentMemory.retrieve` embeds live query text with the same model and query input type, then executes
`$vectorSearch` with a VERIFIED, synthetic and model filter, optional source filter, and top-3 results.
It returns real incident IDs, scores, resolutions and an allowlisted read-only next-check suggestion.
It reports PENDING for missing credentials, missing/unready index, missing embeddings or service failures;
it reports DISABLED for `MEMORY_ENABLED=false`. There is no fabricated/local similarity fallback.
Memory does not authorize amendments or supply authoritative account data.

## Commands

From the repository root (Python 3.12+; this Mac was verified with 3.13.2):

```bash
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install -e 'backend[dev]'
cd backend
.venv/bin/python scripts/setup_atlas.py
.venv/bin/python scripts/verify_atlas.py
```

With uv installed, `cd backend && uv sync --extra dev` and `uv run python scripts/setup_atlas.py`
are equivalent. Setup requires `MONGODB_SETUP_URI`; verification/runtime use `MONGODB_URI`.
After adding the Voyage key, run setup again to seed real embeddings. Once the vector index is queryable:

```bash
.venv/bin/python scripts/verify_atlas.py --require-memory
```

The strict memory check requires the real query “directory payload moved the account field” to return
INC-004 first. A normal verify run can pass the core while explicitly showing memory PENDING; that is
not a passing retrieval proof. If the index is still building, rerun after Atlas reports it queryable.

Tests and static checks:

```bash
.venv/bin/pytest -m 'not atlas' -q
RUN_ATLAS_TESTS=1 .venv/bin/pytest -m atlas -q
.venv/bin/ruff check .
.venv/bin/ruff format --check .
```

Atlas tests use UUID-derived case IDs in tradeops and clean up only their exact synthetic records.
They never drop databases or modify the canonical demo case. Both database users are deliberately
restricted to tradeops, so arbitrary throwaway databases require separately authorized credentials.

Offline tests disable dotenv loading and use `tests/conftest.py` to clear exported application settings
temporarily. This prevents developer/CI API keys and model flags from changing unit-test expectations.
Tests marked `atlas` retain real settings. The demo and verification scripts continue to load the real
environment/.env; no terminal variables or saved credentials are removed outside the test process.

## Verification and remaining work

Verified on the organizer Cluster0: **all 23 tests (15 local + 8 real Atlas)**, plus the runtime
verification script. The same database checks also passed earlier against the free development cluster. Live checks prove
majority+j write/read, one winner under competing version updates, invalid schema rejection, unique
case/operation enforcement, a bounded UTC timeline, stale-run protection, scoped runtime access, and a
persisted checkpoint recovered by a new Python subprocess with the exact same operation payload.

The API, real workflow worker, three simulators and frontend are not built in this database setup session.
The subprocess test proves database persistence across processes; it does **not** prove a custodian
mutation happened exactly once or that a crashing workflow worker resumed. Those remain application
acceptance tests. Atlas alone cannot guarantee exactly-once effects in the separate custodian database.

Voyage credentials, all 9 incident embeddings and real INC-004 first ranking have now been verified.
Retrieval-guided directory adaptation remains pending until the actual worker/adapters are built.
Organizer Sandbox identity and runtime migration are confirmed; verification is recorded above.

The move to the organizer workspace is complete for core MongoDB setup. For any future environment,
create equivalent scoped users/network entries, update only local URI/project/cluster settings and rerun
setup/verification. Do not delete the retained development cluster without explicit authorization.

If connection checks fail after switching Wi-Fi or using another teammate's machine, add that machine's
current public IP to Atlas Network Access. Credentials are local to this Mac; teammates create their own
gitignored `.env`. Never commit or send the generated connection URI through a public repository.
