import type { CaseDoc, Proof } from "../lib/api";
import { time } from "./ui";

export function ProofPanel({ proof, error, caseDoc }: { proof: Proof | null; error: string | null; caseDoc: CaseDoc | null }) {
  const verified = caseDoc?.stage === "VERIFIED";
  const matching = verified && !error && proof?.receiptCount === 1 && proof.revisions.length === 2
    && caseDoc.verification?.receiptId === proof.receipts[0]?.receiptId
    && caseDoc.operation?.operationId === proof.receipts[0]?.operationId;
  return <section className="confirmation" aria-label="Custodian confirmation">
    <div className={`outcome-icon ${matching ? "success" : ""}`}>{matching ? "✓" : "↻"}</div>
    <h1>{matching ? "Correction confirmed" : "Confirming the custodian’s records"}</h1>
    <p>{matching ? `The custodian accepted the instruction with receiving account ${proof.currentAccount}. The saved correction and independent confirmation agree.` : "We’re checking the recorded correction and the current instruction before closing this case."}</p>
    {error && <p role="alert" className="notice warning">Live custodian evidence is unavailable. The last saved case remains visible; confirmation below may be out of date.</p>}
    {proof && <div className="receipt-sheet">
      <div className="receipt-heading"><span>Custodian confirmation</span><span>{proof.status === "ACCEPTED" ? "Accepted for processing" : "Awaiting acceptance"}</span></div>
      <dl className="receipt-fields"><div><dt>Receiving account</dt><dd>{proof.currentAccount}</dd></div><div><dt>Instruction revision</dt><dd>{proof.revisions[0]?.revision ?? "—"}{proof.currentRevision !== proof.revisions[0]?.revision ? ` → ${proof.currentRevision}` : ""}</dd></div><div><dt>Recorded corrections</dt><dd>{proof.receiptCount}</dd></div><div><dt>Submissions received</dt><dd>{proof.patchRequestCount}</dd></div></dl>
      {matching && <p className="confirmation-line">✓ One recorded correction{proof.patchRequestCount === 1 ? " · no duplicate submission" : ""}{caseDoc.verification?.resumedByWorkerId ? " · confirmed after recovery" : ""}</p>}
      {!matching && proof.receiptCount > 0 && <p className="notice warning">A correction is recorded. Independent verification is still pending.</p>}
    </div>}
    {matching && <p className="muted">Confirmed at {time(caseDoc.verification?.verifiedAt)}. Accepted for processing; final securities settlement is outside this demonstration.</p>}
    <details className="technical"><summary>Inspect verification evidence</summary>
      <p>Saved by {caseDoc?.checkpoint?.savedByWorkerId ?? "—"} · resumed by {caseDoc?.verification?.resumedByWorkerId ?? "—"}</p>
      <pre>{JSON.stringify({ operation: caseDoc?.operation, verification: caseDoc?.verification, custodian: proof }, null, 2)}</pre>
    </details>
  </section>;
}
