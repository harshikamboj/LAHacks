# ProofStep / TradeOps Reconciler

**MongoDB Agents in Context Toronto — Track 3: Finish the Job**

ProofStep is the durable workflow control layer. TradeOps is its demonstration: investigate a rejected
settlement instruction, approve one exact account amendment, apply it, and verify the effect after a
lost reply and a real worker crash. The Operations Console is the React workbench.

The complete local demo is implemented. It uses the organizer's MongoDB Atlas Sandbox for checkpoints,
policy, real Vector Search and **66,693 SEC market observations**. Broker trades, accounts, custodian
instructions and receipts are fictional, in three independent SQLite-backed simulators. No real
financial transaction occurs. `ACCEPTED` means accepted for processing, not finally settled.

## What to show

| Track question | Observable behavior |
|---|---|
| Did it take effect, or was it only sent? | Worker reads both the custodian receipt and instruction, comparing the saved operation, payload hash, account, revision, status and trade facts before `VERIFIED`. |
| Can it resume after a crash? | Atlas majority+j intent exists before PATCH. Restarted worker loads the same operation and verifies it. Lost-reply demo finishes with **1 receipt, 1 PATCH, revision 2**. |
| Can it handle a changed system? | Pause mid-investigation, change directory v1 to v2, continue. Actual Voyage/Atlas retrieval returns a verified incident; the investigator reads `/contract` and uses the validated v2 adapter. |

The investigator is deterministic with allowlisted read-only tools; there is no generative LLM in this
MVP. Real Voyage embeddings and Atlas Vector Search guide contract discovery. Memory never authorizes a
write or supplies the authoritative receiving account.

## Dataset and scenario

The supplied JSONL file contains public SEC aggregate outstanding delivery failures. It does not identify
our fictional trade or explain why it failed. Import preserves BSON dates and Decimal128 prices.
The worker joins by verified **CUSIP + settlement date**, not ticker alone.

| Record | Demo value |
|---|---|
| Market context | `F92124100:2026-09-15`, TTE, 1,277 market-wide shares, prior close 91.14 |
| Broker | `TR-2041`, `P-17`, BUY 100 TTE @ USD 91.20, EXECUTED |
| Custodian | `SI-2041`, revision 1, REJECTED, `SAFE-100` |
| Directory | `SAFE-100` retired; `SAFE-401` active and authorized; mapping revision 7 |
| Approved effect | Revision 2, `SAFE-401`, ACCEPTED, one durable receipt |

Correcting the simulated instruction never changes the public observation. The large supplied dataset
stays outside Git. Its source is the [SEC fails-to-deliver dataset](https://www.sec.gov/data-research/sec-markets-data/fails-deliver-data),
archive `cnsfails202609b.zip`.

## Setup and run

Requires Python 3.12+ (verified with 3.13), Node 18+, Atlas network access, and your own root `.env`.
On this development Mac the environment is already configured. Preserve its credentials.

```bash
cp .env.example .env  # only on a new machine; fill Atlas runtime/setup URIs and Voyage key
./scripts/setup.sh /absolute/path/market_fail_observations.json
```

Setup installs dependencies, generates missing local demo tokens, creates schema/indexes/seeds, reuses
unchanged incident embeddings, and imports all observations with idempotent `_id` upserts.

Run from the repository root in separate terminals:

```bash
./scripts/dev.sh       # API :8000, simulators :8101/:8102/:8103, frontend :3000
./scripts/reset.sh     # run once services are ready; stops the tracked local worker if running
./scripts/worker.sh    # keep in a separate terminal; restart this after the deliberate crash
```

Open **http://localhost:3000**. Sign in with `DEMO_REVIEWER_TOKEN` from your local `.env` (copy the value
without surrounding quotes). Do not put it in frontend source or a recording. Login uses an HttpOnly,
SameSite cookie and server-configured reviewer identity. It is local demo authentication, not SSO.

Follow [the three-minute demo guide](docs/demo-script.md). Reset requires a stopped worker, archives the
previous run in Atlas, and preserves market data, incidents and policy.

## Validation

**66 tests passed** against the organizer Atlas: 49 offline, 8 database integration, 9 real-process
workflow tests. Coverage includes real exit-137 recovery after commit and before send, stale/denied
approval, changed mapping revision, unavailable verification reads, unknown schema, mismatched trade
facts, no-action, reset protection and live retrieval-guided v2 adaptation. Frontend production build,
Ruff, formatting and whitespace checks passed. Browser rehearsal also completed the full lost-reply
crash/restart flow with one receipt and one PATCH.

```bash
cd backend
.venv/bin/pytest -m 'not atlas' -q
RUN_ATLAS_TESTS=1 .venv/bin/pytest -m 'atlas and not workflow' -q
RUN_ATLAS_TESTS=1 RUN_WORKFLOW_TESTS=1 .venv/bin/pytest -q
.venv/bin/python scripts/verify_atlas.py --require-memory
.venv/bin/ruff check .
.venv/bin/ruff format --check .
```

Live workflow tests use unique synthetic IDs, temporary SQLite files and separate ports; cleanup is
scoped to their own records. They preserve the canonical demo and market collection. Frontend:
`cd frontend && npm run build`.

## Project references

- [Architecture and recovery rules](docs/architecture.md)
- [HTTP contracts](docs/api-contracts.md)
- [Atlas setup, collections and dataset queries](docs/mongodb-setup.md)
- [Demo steps and presenter narrative](docs/demo-script.md)
- [Current agent handoff](docs/AI_CONTEXT.md)

This is a local hackathon demo with simulated authorities. Exactly-once business effect depends on the
custodian's transactional idempotency contract as well as Atlas checkpointing; Atlas alone cannot
provide that guarantee across a separate external database.
