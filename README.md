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

## Status

Early build. See [docs/AI_CONTEXT.md](docs/AI_CONTEXT.md) for what is implemented and verified.
Run instructions will be added here as components land.

## Configuration

Copy `.env.example` to `.env` and fill in values. Never commit `.env`.

## Team / originality

Created during the hackathon by the team. All code and fixtures in this repository are original work from the event.
