# Multi-case demo and learning loop

The work queue contains four independent fictional instructions with their own trade IDs, stages,
approvals, stable operations and custodian proof. The worker processes only cases in its configured
demo scope; selecting a case remounts its frontend data polls so records cannot bleed between cases.

| Case | Scenario | Outcome |
|---|---|---|
| SI-2041 / TR-2041 | 100 TTE shares, retired SAFE-100 | Approve SAFE-401, apply, independently verify; publish verified experience |
| SI-2042 / TR-2042 | New 150-share TTE trade with a similar account exception | Retrieve actual learned experience, proactively check live directory format, then require a new approval |
| SI-2043 / TR-2043 | 75 shares, already ACCEPTED on SAFE-401 | NO_ACTION; zero new submissions and no learned amendment |
| SI-2044 / TR-2044 | Broker 80 shares vs custodian 800 | MANUAL_REVIEW; no account amendment and no learned resolution |

All refer to the real TTE SEC observation by CUSIP/date for context. These are synthetic operational
scenarios, not individual transactions recovered from the aggregate SEC dataset.

## Suggested presentation

1. Open http://localhost:3000. Select the first case. Sign in if needed.
2. Start reconciliation. At the pause, optionally use Demo controls → Updated format; close and Continue.
3. Review the independently read directory reference (SAFE-401/P-17/Active/Authorized) beside the proposal.
   Approve, then apply. The original lost-confirmation/crash/restart demonstration still works here.
4. Wait for **Correction confirmed**, then **Verified experience saved**. Confirmation and memory
   publication are separate facts. A provider failure never turns a pending memory into a success.
5. Return to the work queue. The similar follow-up becomes actionable only after the first case is
   VERIFIED and learning is STORED. The API also enforces this prerequisite (409 EXPERIENCE_NOT_READY).
6. Open SI-2042 and start reconciliation. It has no default directory pause. Show **Learned from completed
   case SI-2041** with the actual similarity score. The contract check precedes its first account read;
   unlike the first changed-format case, it does not first fail using the old account field.
7. Inspect the fresh 150-share trade and independent current account evidence. Approve and apply this
   case separately. It receives a distinct operation and receipt. Previous approval is never inherited.
8. Return to the queue and open SI-2043: start → No correction needed. Then SI-2044: start → Specialist
   review needed, with the 80-vs-800 discrepancy shown. Neither publishes a successful resolution.

The work queue is an actionable list of cases, not an analytics dashboard. Technical evidence remains
expandable; the main task uses business language.

## What “learning” means

The worker first majority-saves VERIFIED with independent receipt/instruction evidence and a PENDING
learning outbox in the same case update. A later worker step checks that proof again, creates a stable
`INC-LEARN-<caseId>-<runId>` document, obtains a real Voyage document embedding and upserts the incident.
An interrupted publication retries the same incident ID. Only after persistence does the case say STORED.

The learned document records source case/run, portfolio, verified receipt/operation/payload hash and
account, plus a reusable safe procedure. The procedure suggests a read-only live contract check; it
never supplies an authoritative new account, approval or permission to skip policy.

On the next similar rejected-account case, actual Voyage query embeddings + Atlas Vector Search retrieve
verified learned incidents. The source prefilter is `directory:<demoOwner>`, using the existing indexed
source field, followed by portfolio/provenance/score checks. The newest eligible retrieved match with
score ≥ 0.70 may guide the contract check. Raw results and actual guidedBy are stored in investigation.
If no eligible match is retrieved, the normal read-only investigation remains the fallback, with no
claim that learning was used. Unsupported live formats still stop for specialist review.

Query vectors are cached for 10 minutes within a worker (bounded 32 entries); search results are always
fresh. Embedding/rate-limit failures stay explicit. Publication has 3 bounded attempts with 60-second
spacing; lookup retries index warm-up 3 seconds or rate limits 60 seconds, then safely falls back.
STORED means the real vector is persisted; Atlas search indexing can lag briefly.

Reset archives all four runs, resets fictional simulator data and rotates run IDs. It preserves learned
experience and public market data. Thus a later rehearsal can benefit from an earlier verified run;
source run/receipt provenance remains inspectable. There is no model fine-tuning or generic self-training.

Product framing: **TradeOps** is the financial application and the name shown in its interface.
**ProofStep** is the control-layer architecture/methodology implemented over the TradeOps workflow.
Present the TradeOps case lifecycle, then explain how the ProofStep layer provides durable intent,
policy/approval gates, recovery, verified completion and reusable verified experience for Track3.

If publication exhausts its bounded attempts, the case remains confirmed and the follow-up stays
locked. “Retry saving experience” requests another publication budget with authenticated/versioned
control; it cannot resubmit the correction. This handles a recovered provider without inventing memory.

Validation: the real two-case process test passed through both independent approvals/executions with
different operation and receipt IDs, one submission per instruction, real retrieval and publication
retry. In the browser, SI-2041 published verified experience and SI-2042 retrieved it with score 0.859;
the live follow-up is intentionally left awaiting human approval with zero submissions. The other
two queue cases showed NO_ACTION and manual referral respectively, with zero corrections.
