import { useState } from "react";
import { api } from "../lib/api";
import type { CaseDoc } from "../lib/api";
import { Card, Empty, Field, Pill, time } from "./ui";

const ENGINE_PENDING =
  "The case engine (workflow worker + Atlas case store) isn't connected yet. " +
  "Investigation, approval and the live timeline appear here once it is.";

export function AgentPanel({ caseDoc, authenticated, onChange }: {
  caseDoc: CaseDoc | null; authenticated: boolean; onChange: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  async function action(fn: () => Promise<unknown>) {
    setBusy(true); setMessage("");
    try { await fn(); } catch (e) { setMessage(e instanceof Error ? e.message : "Action failed"); }
    finally { setBusy(false); onChange(); }
  }
  const pending = !caseDoc;
  const steps = caseDoc?.investigation?.steps ?? [];
  const precedent = caseDoc?.investigation?.precedents?.find((p) => p.status === "FOUND");
  const proposal = caseDoc?.proposal;
  const events = caseDoc?.events ?? [];

  return (
    <div className="grid-2">
      <div className="stack">
        <Card title="Agent investigation" aside={<Pill tone="muted">read-only tools</Pill>}>
          {caseDoc?.stage === "NEW" && <button className="primary" disabled={!authenticated || busy}
            onClick={() => action(() => api.start(caseDoc.version))}>Start investigation</button>}
          {message && <p role="alert" className="bad-text">{message}</p>}
          {pending ? <Empty>{ENGINE_PENDING}</Empty>
            : steps.length === 0 ? <Empty>Not started. Click Investigate to begin.</Empty>
            : (
              <ol className="steps">
                {steps.map((s) => (
                  <li key={s.n} className={s.ok ? "" : "step-warn"}>
                    <span className="mono">{s.tool}</span>
                    <span className="step-summary">{s.summary}</span>
                    {s.guidedBy && <Pill tone="info">guided by {s.guidedBy}</Pill>}
                  </li>
                ))}
              </ol>
            )}
          {precedent && (
            <p className="precedent">
              Precedent <span className="mono">{precedent.incidentId}</span>
              {precedent.score !== undefined && ` (score ${precedent.score.toFixed(2)})`} from Atlas Vector Search
            </p>
          )}
          {caseDoc?.investigation?.diagnosis && <p className="diagnosis">{caseDoc.investigation.diagnosis}</p>}
        </Card>

        <Card title="Approval" aside={<Pill tone="muted">exact change only</Pill>}>
          {!proposal ? <Empty>No proposal yet.</Empty> : (
            <>
              <dl>
                <Field label="Instruction">{String(proposal.instructionId)} · expected rev {proposal.expectedRevision}</Field>
                <Field label="Change">{proposal.oldAccount} → {proposal.newAccount}</Field>
                <Field label="Policy">{proposal.policyVersion} · mapping revision {String(proposal.mappingRevision)}</Field>
                <Field label="Hash">{caseDoc?.proposalHash}</Field>
              </dl>
              {caseDoc?.stage === "AWAITING_APPROVAL" && <div className="actions">
                <button className="primary" disabled={!authenticated || busy}
                  onClick={() => action(() => api.decision(caseDoc.version, caseDoc.proposalHash!, "APPROVE"))}>Approve exact correction</button>
                <button className="danger" disabled={!authenticated || busy}
                  onClick={() => action(() => api.decision(caseDoc.version, caseDoc.proposalHash!, "DENY"))}>Deny correction</button>
              </div>}
              {caseDoc?.stage === "APPROVED" && <button className="primary" disabled={!authenticated || busy || caseDoc.executionRequested}
                onClick={() => action(() => api.execute(caseDoc.version))}>Apply approved correction</button>}
              {caseDoc?.stage === "AWAITING_VERIFICATION" && <p className="pending-proof">Outcome pending · worker must read the receipt and instruction before closing.</p>}
              {caseDoc?.stage === "DENIED" && <p className="bad-text">Denied. No amendment will be sent.</p>}
              {caseDoc?.approval && (
                <p className="ok-text">Decision by {caseDoc.approval.reviewerId} at {time(caseDoc.approval.approvedAt)}</p>
              )}
            </>
          )}
        </Card>
      </div>

      <Card title="Live timeline">
        {pending ? <Empty>Events from the Atlas case document will stream here.</Empty>
          : events.length === 0 ? <Empty>No events yet.</Empty>
          : (
            <ol className="timeline">
              {[...events].reverse().map((e, idx) => (
                <li key={`${e.at}-${idx}`}>
                  <span className="mono when">{time(e.at)}</span>
                  <span className="what">{e.type.replace(/_/g, " ").toLowerCase()}</span>
                  <span className="detail">{e.actor && <strong>{e.actor} · </strong>}{e.detail}</span>
                </li>
              ))}
            </ol>
          )}
        {caseDoc?.manualReview && (
          <p className="bad-text">Manual review: {caseDoc.manualReview.code} — {caseDoc.manualReview.detail}</p>
        )}
      </Card>
    </div>
  );
}
