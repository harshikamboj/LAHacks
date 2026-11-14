# 3-minute live demo script

Setup (before judges arrive): terminals running `scripts/dev.sh` (3 simulators + API), `scripts/worker.sh`,
and `cd frontend && npm run dev`. Open http://localhost:5173. Click **Reset Demo**.

| Time | Presenter action | What the screen proves |
|---|---|---|
| 0:00–0:30 | Open case SI-2041. | Three **simulated** source-of-truth cards with live API reads: broker `TR-2041` EXECUTED, custodian `SI-2041` rev 1 REJECTED on `SAFE-100`, directory says `SAFE-100` retired. "Three systems, three owners." |
| 0:30–1:10 | Failure lab → switch directory to **v2**. Click **Investigate**. | Agent panel lists each read-only tool call. The v1 adapter fails on the new shape → Atlas Vector Search returns precedent `INC-004` ("account field moved") → its suggested next check is `GET /contract` → v2 adapter validates `SAFE-401`. Proposal `SAFE-100 → SAFE-401`, rev 1, policy v1, hash shown. |
| 1:10–1:30 | Click **Approve** (demo reviewer). | Approval bound to the exact hash. Nothing was sent to the custodian before this (proof panel: 0 PATCH requests). |
| 1:30–2:20 | Failure lab → enable **Lost custodian response** + **Crash worker on unknown outcome**. Click **Apply Approved Correction**. | Timeline: `INTENT_PERSISTED` (Atlas, majority write) → `PATCH_SENT`. Custodian commits rev 2 + receipt, then drops the reply. Worker pill turns **offline** — the worker process really exited (terminal shows exit 137). Case stays `AWAITING_VERIFICATION`: outcome uncertain, not failed. |
| 2:20–2:45 | In the worker terminal run `scripts/worker.sh` again. | New worker ID (new PID) logs `RESUMED_FROM_CHECKPOINT` with the **same operationId** from Atlas → reads `/operations/{id}` and `/instructions/SI-2041` → `VERIFIED`. **No second PATCH.** |
| 2:45–3:00 | Point at the proof panel. | Receipt count **1**, PATCH requests **1**, revision **1 → 2**, status `ACCEPTED`, checkpoint saved by worker A, resumed by worker B. "We don't just send the fix. We prove it happened once — even after the agent dies." |

Backup beats (if asked): switch directory to **v3** and investigate → `MANUAL_REVIEW UNKNOWN_DIRECTORY_CONTRACT`;
click Approve twice → second click 409 `STAGE_CONFLICT`.

One-minute video: record 1:30–3:00 (the crash and recovery).
