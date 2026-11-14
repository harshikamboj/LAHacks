# Problem statement and presentation positioning

## Primary challenge: 3. Finish the Job

Settlement operations teams must complete an approved correction across independent systems even when
an external response is lost, processing crashes, or a system changes its record format mid-task.
They need to know whether the correction actually took effect and resume safely without making a
duplicate change or repeating the entire investigation.

**Presentation statement:** “ProofStep completes approved settlement corrections across changing systems,
survives interruptions, and independently verifies what actually happened.”

TradeOps demonstrates one complete receiving-account reconciliation: rejected instruction → cross-system
investigation → validated correction → exact human approval → application → independent confirmation.
The workflow ends at accepted for processing. Final securities settlement is outside its scope.

| Finish the Job question | Implemented answer | Demo evidence |
|---|---|---|
| Took effect or merely sent? | Compare original approved operation with the custodian receipt and current instruction. | Correction confirmed only after matching independent reads; receipt and submission counts visible. |
| Resume after a crash without replaying history? | Majority+j Atlas intent and persisted investigation phases, stable operation ID, separate worker. | Real worker exit, restart, saved operation verified with one receipt and one submission. |
| Adapt when fields/workflow change? | Actual Voyage/Atlas Vector Search retrieves a verified incident; investigator reads live contract and uses a validated adapter. | Change Original format to Updated format while paused; account check adapts. Unsupported format is referred for review. |

## Relationship to the other tracks

Track1 (Agents You Can Audit) is supported by server-derived reviewer identity, exact approval, policy
checks and a recorded activity trail. We are not claiming the full track, including general stop/rollback
of arbitrary actions.

Track2 (Memory You Can Govern) contributes the real verified-incident retrieval. We are not claiming a
complete memory-governance product with user-facing tenant permissions, expiry and correction/deletion
management. Memory is used to help finish the job in Track3.

## Evidence and limits to explain honestly

- The full supplied SEC dataset is in Atlas (66,693 observations). CUSIP/date matching provides real
  historical market context, not a per-trade root cause or an account recommendation.
- The demonstrated 100-share TTE trade, accounts, rejection and correction are fictional.
- The investigator is deterministic with real semantic retrieval. It uses two allowlisted adapters;
  it does not generate arbitrary code to repair unknown systems.
- Durable intent in Atlas and transactional idempotency in the custodian simulator jointly protect the
  business effect. MongoDB alone cannot promise exactly-once effects in another independent database.

## Product experience

An operator works through four stages: Review exception → Reconcile records → Authorize correction →
Confirm completion. The main view shows a task, business records and the next available action.
Technical evidence is expandable. Scenario injection belongs in the separate Demo controls drawer.
The frontend is an operational case lifecycle with real mutations in independent simulators, rather
than an analytics display or a collection of monitoring widgets.

## Cross-case demonstration

The operational queue now adds a verified learning loop: first correction → independent confirmation →
real embedded experience → similar follow-up → changed tool order with fresh validation/approval.
An accepted instruction produces NO_ACTION and conflicting quantities require specialist review. The
primary claim remains Track3 dependable completion, with verified memory helping the next task.
See learning-demo.md for exact scenarios and evidence.

Product framing: **TradeOps** is the financial application and the name shown in its interface.
**ProofStep** is the control-layer architecture/methodology implemented over the TradeOps workflow.
Present the TradeOps case lifecycle, then explain how the ProofStep layer provides durable intent,
policy/approval gates, recovery, verified completion and reusable verified experience for Track3.
