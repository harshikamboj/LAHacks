import type { CaseDoc, Health, Sources } from "../lib/api";
import { Pill, type Tone } from "./ui";

const STAGE_TONE: Record<string, Tone> = {
  NEW: "muted", INVESTIGATING: "info", AWAITING_APPROVAL: "info", APPROVED: "info",
  AWAITING_VERIFICATION: "warn", VERIFIED: "ok", MANUAL_REVIEW: "bad", DENIED: "bad", NO_ACTION: "muted",
};

const WORKER_LABEL: Record<string, string> = {
  OFFLINE: "offline", NEVER_STARTED: "not started", UNKNOWN: "unknown (Atlas not connected)",
};

export function CaseHeader({ health, sources, caseDoc, caseError }: {
  health: Health | null; sources: Sources | null; caseDoc: CaseDoc | null; caseError: string | null;
}) {
  const trade = sources?.broker.data;
  const worker = health?.worker;
  return (
    <header className="topbar">
      <div>
        <h1>ProofStep <span className="tagline">TradeOps Reconciler · Finish the Job</span></h1>
        <p className="sub mono">
          Case SI-2041
          {trade && ` · ${trade.tradeId} · ${trade.portfolioId} · ${trade.side} ${trade.quantity} ${trade.security} @ ${trade.currency} ${trade.price}`}
        </p>
      </div>
      <div className="pills" aria-live="polite">
        {caseDoc ? (
          <Pill tone={STAGE_TONE[caseDoc.stage] ?? "muted"}>{caseDoc.stage.replace(/_/g, " ").toLowerCase()}</Pill>
        ) : (
          <Pill tone="muted" >{caseError ?? "loading case"}</Pill>
        )}
        {health ? (
          worker?.online ? <Pill tone="ok">{worker.workerId ?? "worker"} online</Pill>
            : <Pill tone="bad">worker {WORKER_LABEL[worker?.status ?? ""] ?? "offline"}</Pill>
        ) : <Pill tone="muted">worker unknown</Pill>}
        {health && (
          <Pill tone={health.atlas.ok ? "ok" : "warn"}>
            Atlas {health.atlas.ok ? "connected" : health.atlas.status.replace(/_/g, " ").toLowerCase()}
          </Pill>
        )}
      </div>
    </header>
  );
}
