import type { CaseDoc } from "../lib/api";
import { Card, Empty, Field, Pill, time } from "./ui";

const ENGINE_PENDING =
  "The case engine (workflow worker + Atlas case store) isn't connected yet. " +
  "Investigation, approval and the live timeline appear here once it is.";

export function AgentPanel({ caseDoc }: { caseDoc: CaseDoc | null }) {
  const pending = !caseDoc;
  const steps = caseDoc?.investigation?.steps ?? [];
  const precedent = caseDoc?.investigation?.precedents?.find((p) => p.status === "FOUND");
  const proposal = caseDoc?.proposal;
  const events = caseDoc?.events ?? [];

  return (
    <div className="grid-2">
      <div className="stack">
        <Card title="Agent investigation" aside={<Pill tone="muted">read-only tools</Pill>}>
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
                <Field label="Policy">{proposal.policyVersion}</Field>
                <Field label="Hash">{caseDoc?.proposalHash}</Field>
              </dl>
              {caseDoc?.approval && (
                <p className="ok-text">Approved by {caseDoc.approval.reviewerId} at {time(caseDoc.approval.approvedAt)}</p>
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
                  {e.detail && <span className="detail">{e.detail}</span>}
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
