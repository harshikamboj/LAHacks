import { useState } from "react";
import { api } from "../lib/api";
import type { CaseDoc, DemoState, Health, Proof, Sources } from "../lib/api";
import { eventLabels, friendlyError, toolLabels } from "../lib/presentation";
import { time } from "./ui";
import { ProofPanel } from "./ProofPanel";

export function AgentPanel({ caseDoc, authenticated, onChange, health, demo, proof, proofError, sources, onBack }: {
  onBack: () => void; caseDoc: CaseDoc | null; authenticated: boolean; onChange: () => void; health: Health | null;
  demo: DemoState | null; proof: Proof | null; proofError: string | null; sources: Sources | null;
}) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  async function action(fn: () => Promise<unknown>) {
    setBusy(true); setMessage("");
    try { await fn(); } catch (e) { setMessage(friendlyError(e)); }
    finally { setBusy(false); onChange(); }
  }
  if (!caseDoc) return <section className="workspace"><span className="eyebrow">Reconciliation case</span><h1>Loading the instruction…</h1><p>Connecting to the saved case and its supporting records.</p></section>;
  const stage = caseDoc.stage;
  const steps = caseDoc.investigation?.steps ?? [];
  const proposal = caseDoc.proposal;
  const precedent = caseDoc.investigation?.precedents?.find(p => p.status === "FOUND");
  const events = caseDoc.events ?? [];
  const offline = health && !health.worker.online;
  const blocked = !authenticated || busy;
  const trade = sources?.broker.data;
  const needsService = offline && ["NEW", "INVESTIGATING", "APPROVED", "AWAITING_VERIFICATION"].includes(stage);

  return <>
    <section className="workspace" aria-label="Current reconciliation step" aria-busy={busy}>
      {message && <p role="alert" className="notice warning">{message}</p>}
      {needsService && <div role="status" className="notice warning"><strong>Reconciliation service paused.</strong> The saved case is preserved. {stage === "AWAITING_VERIFICATION" ? "Resume the service to confirm the existing correction before taking another action." : "Resume the service to continue processing."}<details><summary>How to resume this local demo</summary><p>In the project terminal, run:</p><code>./scripts/worker.sh</code></details></div>}
    {caseDoc.investigation?.reusedExperience && <aside className="experience-note"><strong>Learned from completed case {caseDoc.investigation.reusedExperience.learnedFromCaseId}</strong><p>The retrieved procedure changed this investigation: TradeOps checked the live directory format first, before reading the account. Current eligibility and a fresh approval are still required.</p><small>Actual semantic similarity: {caseDoc.investigation.reusedExperience.score.toFixed(2)}</small></aside>}
      {stage === "NEW" && <>
        <span className="eyebrow">01 / Review exception</span><h1>{caseDoc.scenarioKind === "already_accepted" ? "Confirm an accepted instruction." : caseDoc.scenarioKind === "trade_mismatch" ? "Trade records need reconciliation." : "A receiving account needs attention."}</h1>
        <p className="lead">{caseDoc.scenarioKind === "already_accepted" ? "Check the current custodian record to establish whether any correction is needed." : "Reconcile the trade and account records to establish the safe next action for this instruction."}</p>
        <div className="exception-document"><div className="document-label">Settlement exception <span>{caseDoc.caseId}</span></div>
          <h2>{trade ? `${trade.side === "BUY" ? "Buy" : trade.side} ${trade.quantity} shares of ${trade.security}` : "Trade details loading"}</h2>
          <dl className="trade-facts"><div><dt>Portfolio</dt><dd>{trade?.portfolioId ?? "—"}</dd></div><div><dt>Settlement date</dt><dd>{trade?.settlementDate ?? "—"}</dd></div><div><dt>Trade price</dt><dd>{trade ? `${trade.currency} ${trade.price}` : "—"}</dd></div><div><dt>Recorded account</dt><dd>{sources?.custodian.data?.safekeepingAccount ?? "—"}</dd></div></dl>
          <p className="exception-reason"><span>!</span>{sources?.custodian.data?.status === "ACCEPTED" ? "The instruction is already accepted; check before making any change." : caseDoc.scenarioKind === "trade_mismatch" ? "Compare the broker trade quantity with the custodian instruction." : sources?.directory.baselineAccountStatus?.status === "RETIRED" ? "The recorded receiving account has been retired." : "The custodian could not accept the recorded receiving account."}</p>
        </div>
        <div className="next-action"><button className="primary" disabled={blocked || !health?.worker.online} onClick={() => action(() => api.start(caseDoc.version, caseDoc.caseId))}>{busy ? "Starting…" : "Start reconciliation →"}</button><small>Checks supporting records. No instruction is changed.</small></div>
      </>}
      {stage === "INVESTIGATING" && <>
        <span className="eyebrow">02 / Reconcile records</span><h1>{demo?.directoryPaused ? "Ready to check the receiving account." : "Building a verified correction."}</h1>
        <p className="lead">TradeOps checks the instruction, executed trade and account eligibility across their independent owners.</p>
        <ol className="reconciliation-checks">{steps.map(s => <li key={s.n} className={!s.ok ? "changed" : ""}><span className="check-icon">{s.ok ? "✓" : "↗"}</span><div><strong>{!s.ok && s.tool === "get_directory_account" ? "Account record format changed" : toolLabels[s.tool] ?? "Checked a supporting record"}</strong>{!s.ok && <p>Inspecting the current directory format before selecting an account.</p>}{s.guidedBy && <p>A verified past case guided this check.</p>}</div></li>)}</ol>
        {caseDoc.investigation?.experienceWaiting && <p className="notice">Retrieving verified past experience. Progress is saved and no correction has been submitted.</p>}
        {precedent && <div className="experience-note"><strong>Relevant past experience found</strong><p>A similar verified case helps guide the account-directory check. Current records still determine the correction.</p></div>}
        {demo?.directoryPaused ? <div className="pause-action"><p><strong>Trade records checked.</strong> Continue to validate the current receiving account.</p><button className="primary" disabled={blocked} onClick={() => action(() => api.setFaults({pauseDirectoryRead: false}, caseDoc.caseId))}>Continue reconciliation →</button></div> : !offline && <p className="processing" role="status"><span /> Checking records and saving progress…</p>}
      </>}
      {proposal && ["AWAITING_APPROVAL", "APPROVED", "DENIED"].includes(stage) && <>
        <span className="eyebrow">03 / Authorize correction</span><h1>{stage === "APPROVED" ? "Approved and ready to apply." : stage === "DENIED" ? "Correction declined." : "Review the receiving-account correction."}</h1>
        <p className="lead">{stage === "DENIED" ? "This proposal was declined. No amendment will be sent." : "The proposed change updates the receiving account on this instruction. The trade’s security, quantity and portfolio stay the same."}</p>
        <div className="amendment"><div><span className="eyebrow">Current account</span><strong>{proposal.oldAccount}</strong><small>Retired receiving account</small></div><span className="amendment-arrow">→</span><div><span className="eyebrow">Proposed account</span><strong>{proposal.newAccount}</strong><small>Active and authorized for this portfolio</small></div></div>
        {caseDoc.evidence?.activeAccount && <div className="directory-reference"><span className="eyebrow">Independent account-directory reference</span><strong>{caseDoc.evidence.activeAccount.accountId}</strong> · Portfolio {caseDoc.evidence.activeAccount.portfolioId} · {caseDoc.evidence.activeAccount.status === "ACTIVE" ? "Active" : caseDoc.evidence.activeAccount.status} · {caseDoc.evidence.activeAccount.authorized ? "Authorized" : "Not authorized"}<small>Read from the directory during this investigation. Checked again before applying the correction.</small></div>}
        <p className="approval-scope">Applies to instruction <strong>{String(proposal.instructionId)}</strong>, revision <strong>{proposal.expectedRevision}</strong>. Any change to the approved inputs requires another review.</p>
        {!caseDoc.investigation?.reusedExperience && steps.some(s => s.guidedBy) && <p className="experience-note">A verified past case guided the directory-format check. The current receiving account was then validated against live records.</p>}
        {stage === "AWAITING_APPROVAL" && <div className="next-action"><div className="actions"><button className="primary" disabled={blocked} onClick={() => action(() => api.decision(caseDoc.version, caseDoc.proposalHash!, "APPROVE", caseDoc.caseId))}>Approve correction</button><button className="quiet danger" disabled={blocked} onClick={() => action(() => api.decision(caseDoc.version, caseDoc.proposalHash!, "DENY", caseDoc.caseId))}>Decline</button></div><small>Approval authorizes this change. Applying it is a separate step.</small></div>}
        {caseDoc.approval && <p className="reviewer-decision">{stage === "DENIED" ? "Declined" : "Approved"} by {caseDoc.approval.reviewerId} at {time(caseDoc.approval.approvedAt)}.</p>}
        {stage === "APPROVED" && <div className="next-action"><button className="primary" disabled={blocked || !!caseDoc.executionRequested || !health?.worker.online} onClick={() => action(() => api.execute(caseDoc.version, caseDoc.caseId))}>{caseDoc.executionRequested ? "Preparing correction…" : "Apply approved correction →"}</button><small>Current account and instruction records are checked again before submission.</small></div>}
        <details className="technical"><summary>Approval evidence</summary><dl><dt>Policy version</dt><dd>{proposal.policyVersion}</dd><dt>Account mapping revision</dt><dd>{String(proposal.mappingRevision)}</dd><dt>Exact proposal fingerprint</dt><dd className="mono">{caseDoc.proposalHash}</dd></dl></details>
      </>}
      {["AWAITING_VERIFICATION", "VERIFIED"].includes(stage) && <><span className="eyebrow">04 / Confirm completion</span><ProofPanel proof={proof} error={proofError} caseDoc={caseDoc} /></>}
      {stage === "MANUAL_REVIEW" && <><span className="eyebrow">Specialist review</span><h1>This case needs a human investigation.</h1><p className="lead">{caseDoc.manualReview?.code === "UNKNOWN_DIRECTORY_CONTRACT" ? "The directory uses an unsupported record format. TradeOps stopped rather than guessing the receiving account." : "The available records could not safely establish the next action. Review the supporting evidence before proceeding."}</p>{caseDoc.scenarioKind === "trade_mismatch" && sources?.broker.data && sources?.custodian.data && <div className="amendment mismatch"><div><span className="eyebrow">Broker trade</span><strong>{sources.broker.data.quantity} shares</strong></div><span className="amendment-arrow">≠</span><div><span className="eyebrow">Custodian instruction</span><strong>{sources.custodian.data.quantity} shares</strong></div></div>}<p className="notice warning">An unresolved case is not marked complete. Check custodian evidence for any correction already recorded.</p><details className="technical"><summary>Review referral details</summary><p>{caseDoc.manualReview?.code} · {caseDoc.manualReview?.detail}</p></details></>}
      {stage === "NO_ACTION" && <><span className="eyebrow">Review complete</span><h1>No correction is needed.</h1><p className="lead">The custodian instruction is already accepted. TradeOps closed the investigation without submitting an amendment.</p></>}
      {!authenticated && <p className="muted">Sign in above to operate this case.</p>}
    </section>
    {stage === "VERIFIED" && <aside className="experience-note" role="status"><strong>{caseDoc.learning?.status === "STORED" ? "Verified experience saved" : (caseDoc.learning?.attempts ?? 0) >= 3 ? "Experience publication needs attention" : "Saving this verified experience"}</strong><p>{caseDoc.learning?.status === "STORED" ? "A later similar case can retrieve this procedure. Its account will be checked independently." : "Experience becomes reusable after embedding and publication. The correction itself is confirmed."}</p>{caseDoc.learning?.reason && <small>Experience publication is pending. The follow-up will unlock once it is saved.</small>}{caseDoc.learning?.status === "PENDING" && (caseDoc.learning.attempts ?? 0) >= 3 && <button disabled={blocked} onClick={() => action(() => api.retryLearning(caseDoc.version, caseDoc.caseId))}>Retry saving experience</button>}</aside>}
    {["VERIFIED", "DENIED", "MANUAL_REVIEW", "NO_ACTION"].includes(stage) && <button className="primary" onClick={onBack}>Return to work queue →</button>}
    <details className="activity-record"><summary>Case activity <span>{events.length} recorded events</span></summary><ol>{[...events].reverse().map((event, i) => <li key={`${event.at}-${i}`}><time>{time(event.at)}</time><span>{eventLabels[event.type] ?? "Case record updated"}</span></li>)}</ol><details className="technical"><summary>ProofStep control record</summary><pre>{JSON.stringify({ events, investigation: caseDoc.investigation }, null, 2)}</pre></details></details>
  </>;
}
