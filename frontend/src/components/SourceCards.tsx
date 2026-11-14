import type { Sources } from "../lib/api";
import { time } from "./ui";

export function SourceCards({ sources, error }: { sources: Sources | null; error: string | null }) {
  return <details className="supporting-records">
    <summary>Review supporting records <span>Broker, account directory and custodian</span></summary>
    {error && sources && <p role="alert" className="notice warning">Live records could not be refreshed. The records below were read earlier and may be out of date.</p>}
    {!sources ? <p className="muted">{error ? "Supporting records are temporarily unavailable." : "Reading supporting records…"}</p> : <>
      <div className="record-row"><div><strong>Executed trade</strong><small>Broker · read {time(sources.broker.fetchedAt)}</small></div><p>{sources.broker.data ? `${sources.broker.data.side === "BUY" ? "Buy" : sources.broker.data.side} ${sources.broker.data.quantity} ${sources.broker.data.security} · ${sources.broker.data.status === "EXECUTED" ? "Trade executed" : sources.broker.data.status}` : "Broker record unavailable"}</p></div>
      <div className="record-row"><div><strong>Receiving-account directory</strong><small>Directory · read {time(sources.directory.fetchedAt)}</small></div><p>{sources.directory.ok ? `Account format ${sources.directory.contract?.version ?? "—"} · ${sources.directory.baselineAccountStatus?.accountId ?? "Account"} ${sources.directory.baselineAccountStatus?.status === "RETIRED" ? "retired" : sources.directory.baselineAccountStatus?.status === "ACTIVE" ? "active" : "status unavailable"}` : "Directory record unavailable"}</p></div>
      <div className="record-row"><div><strong>Settlement instruction</strong><small>Custodian · read {time(sources.custodian.fetchedAt)}</small></div><p>{sources.custodian.data ? `${sources.custodian.data.safekeepingAccount} · ${sources.custodian.data.status === "ACCEPTED" ? "Accepted for processing" : "Rejected"} · revision ${sources.custodian.data.revision}` : "Custodian record unavailable"}</p></div>
      <details className="technical"><summary>Technical source evidence</summary><pre>{JSON.stringify(sources, null, 2)}</pre></details>
    </>}
  </details>;
}
