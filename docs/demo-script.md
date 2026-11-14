# ProofStep / TradeOps: three-minute demo

The operational workflow is implemented. The main page presents one active task at a time, with business terminology. Presenter faults are in the separate Demo controls drawer; technical evidence is expandable. The problem is reliable completion of an
approved action across independent systems when requests time out, workers die and upstream contracts
change. ProofStep supplies durable control; TradeOps demonstrates it with a fictional account correction.

## Before presenting

From the repository root, keep two terminals visible:

```bash
# Terminal A: all HTTP services and frontend; leave running
./scripts/dev.sh
```

```bash
# Terminal B: safe reset, then independent worker
./scripts/reset.sh
./scripts/worker.sh
```

If services are already running, reuse them. Do not start duplicate processes. Reset stops the tracked
local worker, resets the three simulators, archives the previous Atlas case, and creates a new run.
The API refuses reset while any worker holds the lease. After a forced kill, allow about five seconds
for the lease to expire. Public observations, policy and verified incidents survive reset.

Open **http://localhost:3000**, select the first case from the work queue. Sign in with `DEMO_REVIEWER_TOKEN` from the root `.env`, excluding any
surrounding quotes. Keep the token out of recordings. Check Atlas connected, reconciliation service running, case NEW,
Original format selected, zero receipts/PATCHes, Pause before checking account records ON, other faults OFF. If needed on a new
machine, run setup and `backend/.venv/bin/python backend/scripts/verify_atlas.py --require-memory` first.

## Problem statement to present

Primary track: **3. Finish the Job**. “Settlement operations teams must complete an approved correction
across independent systems despite lost replies, processing crashes and changing record formats.
ProofStep resumes from saved work and independently confirms the effect without duplicating it.”
See problem-statement.md for precise positioning against all three tracks.

## Main demonstration

| Time | Action | Narrative and visible evidence |
|---|---|---|
| 0:00–0:25 | Show the settlement exception and trade details. Expand supporting records if needed. Click **Start reconciliation →**. | "This fictional broker executed 100 TTE shares. The custodian rejected its instruction because the receiving account was retired. Each system owns separate data." |
| 0:25–0:45 | Show the attached Market Context card. Wait for **Ready to check the receiving account**. | "We imported all 66,693 supplied SEC observations. Exact CUSIP/date lookup finds TTE, 1,277 market-wide outstanding failed shares, prior close 91.14. This is real historical context; it does not identify or explain our fictional trade." |
| 0:45–1:15 | While paused, open **Demo controls**, select **Updated format**, wait until selected, then close the drawer. Click **Continue reconciliation →**. | "The directory changed during the run. The old parser detects the change. Real Voyage/Atlas retrieval returns INC-004 and a similarity score (in the expandable technical audit), suggesting a contract read. We validate the live `/contract`, use the allowlisted v2 adapter, then verify SAFE-401 is active and authorized." |
| 1:15–1:35 | Review the old/new account and instruction scope. Expand Approval evidence if judges want the exact fingerprint and policy. Click **Approve correction**. | "The human approves this precise proposal. Approval alone sends nothing." Approval alone does not apply a correction. Decline is an alternative terminal decision. |
| 1:35–2:00 | Open **Demo controls** and turn ON **Delay the custodian’s confirmation**. Wait for it to stay checked. Turn ON **Interrupt processing after submission**. Wait for checked state, then close the drawer. Click **Apply approved correction →**. | "The worker rechecks current inputs, saves the exact operation in Atlas with majority+j durability, then sends. The custodian commits instruction + receipt, but its reply arrives after our timeout. The worker really exits 137 before recording the result." |
| 2:00–2:25 | Show Confirming outcome and Reconciliation service paused; Terminal B has exited. Run `./scripts/worker.sh` again in Terminal B. | "The API and three systems stayed alive. A new worker reads the saved checkpoint and reuses the original operation ID. It queries the custodian operation and instruction instead of replaying the amendment." |
| 2:25–3:00 | Show Correction confirmed and the custodian confirmation. | "One receipt, one PATCH, revision 2, SAFE-401, ACCEPTED. Saved-by and resumed-by worker IDs differ. The receipt hash and both read-backs match the approved intent. We proved the approved effect took place once despite the crash." |

Do not also enable **Interrupt before submission** in this main scenario. That is a separate test.
An unavailable operation lookup is also a separate scenario, not the main crash path.

## What each layer contributes

- **Atlas**: active case, version/run guards, approval, majority+j operation intent, evidence, timeline,
  policy, lease, public observations and real incident Vector Search.
- **ProofStep worker**: recoverable tool phases, pre-send checks, single-operation discipline, bounded
  same-key recovery and independent verification. Browser refresh/API polling cannot execute a write.
- **Custodian simulator**: transactional operation receipt + amendment and stable-key idempotency.
  Exactly-once effect requires this receiving-system contract as well as durable intent.
- **Human reviewer**: server-authenticated identity and exact hash approval, then separate execution.

This MVP uses a deterministic investigator and genuine semantic retrieval, not a generative LLM.
Adaptation is bounded to two validated schemas; unrecognized schemas stop for human review.

## Optional safety demonstrations

Reset between alternatives, then restart the worker. Leave pause ON if showing mid-run changes.

| Scenario | Steps | Expected result |
|---|---|---|
| Denial | Start reconciliation, continue Original format, click Decline | DENIED, zero PATCH/receipts |
| Unknown contract | Pause, choose Unsupported format, continue | MANUAL_REVIEW / UNKNOWN_DIRECTORY_CONTRACT, zero PATCH |
| Crash before send | Approve; enable only pre-send crash; apply; restart worker | Durable intent with zero initial PATCH; confirmed absence then original key is sent once and verified |
| Unavailable verification | Enable lost reply + operations lookup unavailable; apply | Bounded verification deferrals then MANUAL_REVIEW, no blind resend |
| Already accepted | Covered in live tests; no UI fixture editor provided | NO_ACTION, zero amendments |
| Stale/altered approval | Covered by live API tests | 409 conflict/hash mismatch; no write |
| Changed mapping after approval | Covered by live process tests | Approval invalidated, fresh proposal required, zero write with old approval |

## Atlas view for judges

Data Explorer → `tradeops`: show the observation `_id` `F92124100:2026-09-15`, active `cases.caseId`
`SI-2041`, its `operation`, `checkpoint`, `verification` and `events`. `case_runs` retains earlier runs.
Search & Vector Search → `incidents` → READY `incident_vector_index`. The workbench shows the actual
retrieved precedent and its live-contract follow-up; index existence alone is not retrieval proof.

## One-minute recording

Prepare directory adaptation + approval before recording. Spend ~10 seconds on the actual retrieved
INC-004 and exact proposal, ~15 seconds arming the two faults/applying, ~15 seconds on real worker exit
and restart, and ~20 seconds on VERIFIED, 1 receipt/1 PATCH and different worker IDs. State the public
context/synthetic trade distinction and ACCEPTED-not-settled boundary in the narration or closing frame.

The project showcases dependable completion of one authorized action. It does not claim to resolve all
market failures, infer an SEC record's root cause, move securities, or confirm final settlement.

## Reading the operational interface

The left rail follows Review exception → Reconcile records → Authorize correction → Confirm completion.
The central task changes with saved backend state. Supporting records, case activity, approval evidence
and verification evidence expand on demand. Public SEC context appears after the CUSIP/date lookup.

The main demo now uses these labels:

- Start reconciliation →
- Demo controls → Updated format → Close → Continue reconciliation →
- Approve correction
- Demo controls → Delay the custodian’s confirmation + Interrupt processing after submission → Close
- Apply approved correction →
- After the real exit, restart ./scripts/worker.sh → Correction confirmed

For the final receipt point to Recorded corrections=1 and Submissions received=1. Expand Inspect
verification evidence to show saved/resumed worker IDs and the original operation. The main page avoids
raw API names; all underlying checkpoint, approval and verification checks remain enforced server-side.

## Follow-up and contrasting cases

After the first Correction confirmed, wait for Verified experience saved, then Return to work queue.
The similar receiving-account exception SI-2042 is now available. Start it and show the actual source
case and score under Learned from completed case. The live contract read now precedes the first account
read; source evidence is current and a separate exact approval is still required for this 150-share trade.
Approve/apply to produce its own receipt, then return to the queue. SI-2043 closes with No correction
needed; SI-2044 displays 80 broker shares vs 800 custodian shares and refers for specialist review.
Those outcomes publish no successful-amendment memory. Detailed sequence: learning-demo.md.

Product framing: **TradeOps** is the financial application and the name shown in its interface.
**ProofStep** is the control-layer architecture/methodology implemented over the TradeOps workflow.
Present the TradeOps case lifecycle, then explain how the ProofStep layer provides durable intent,
policy/approval gates, recovery, verified completion and reusable verified experience for Track3.
