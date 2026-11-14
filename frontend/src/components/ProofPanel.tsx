import type { CaseDoc, Proof } from "../lib/api";
import { Card, Empty, Pill, time } from "./ui";

export function ProofPanel({ proof, error, caseDoc }: { proof: Proof | null; error: string | null; caseDoc: CaseDoc | null }) {
  if (!proof) return <Card title="Proof"><Empty>{error ?? "Reading custodian records…"}</Empty></Card>;
  const first = proof.revisions[0];
  const exactlyOnce = caseDoc?.stage === "VERIFIED" && proof.receiptCount === 1 && proof.revisions.length === 2
    && caseDoc.verification?.receiptId === proof.receipts[0]?.receiptId
    && caseDoc.operation?.operationId === proof.receipts[0]?.operationId;
  return (
    <Card title="Proof · read live from the custodian"
      aside={proof.receiptCount === 0 ? <Pill tone="muted">nothing applied yet</Pill>
        : exactlyOnce ? <Pill tone="ok">applied exactly once</Pill>
        : <Pill tone="warn">committed · verification pending</Pill>}>
      <div className="proof-stats">
        <div><span className="k">Receipts</span><span className="v">{proof.receiptCount}</span></div>
        <div><span className="k">PATCH requests received</span><span className="v">{proof.patchRequestCount}</span></div>
        <div><span className="k">Revision</span><span className="v">{first ? `${first.revision}${proof.currentRevision !== first.revision ? ` → ${proof.currentRevision}` : ""}` : proof.currentRevision}</span></div>
        <div><span className="k">Status</span><span className="v small">{proof.status} · {proof.currentAccount}</span></div>
      </div>
      {proof.receipts.length > 0 && (
        <table className="proof-table">
          <thead><tr><th>Receipt</th><th>Operation</th><th>Revision</th><th>Committed</th></tr></thead>
          <tbody>
            {proof.receipts.map((r) => (
              <tr key={r.receiptId}><td className="mono">{r.receiptId}</td><td className="mono">{r.operationId}</td><td>{r.resultRevision}</td><td>{time(r.committedAt)}</td></tr>
            ))}
          </tbody>
        </table>
      )}
      {proof.patchRequests.length > 0 && (
        <details>
          <summary>Every PATCH the custodian received ({proof.patchRequests.length})</summary>
          <ul className="mono plain">
            {proof.patchRequests.map((p, idx) => <li key={idx}>{time(p.receivedAt)} · {p.idempotencyKey} · {p.outcome}</li>)}
          </ul>
        </details>
      )}
      {caseDoc?.verification?.verifiedAt && <p className="ok-text">Independent operation and instruction reads verified at {time(caseDoc.verification.verifiedAt)}.</p>}
      {caseDoc?.checkpoint && (
        <p className="meta">
          Atlas checkpoint saved by <span className="mono">{caseDoc.checkpoint.savedByWorkerId}</span>
          {caseDoc.verification?.resumedByWorkerId && <> · resumed by <span className="mono">{caseDoc.verification.resumedByWorkerId}</span></>}
        </p>
      )}
    </Card>
  );
}
