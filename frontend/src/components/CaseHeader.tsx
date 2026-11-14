import type { CaseDoc, Health } from "../lib/api";
import { stageLabels } from "../lib/presentation";
import { Pill } from "./ui";

export function CaseHeader({ health, caseDoc, onDemo }: { health: Health | null; caseDoc: CaseDoc | null; onDemo: () => void }) {
  return <header className="product-header">
    <a className="brand" href="/" aria-label="TradeOps home"><span className="brand-mark">T<span>↗</span></span><strong>TradeOps</strong><span className="brand-divider" /><span>Settlement operations</span></a>
    <div className="header-actions">
      <span className={`connection ${health?.atlas.ok ? "connected" : ""}`}>{health?.atlas.ok ? "Case saved in Atlas" : "Connecting to case records"}</span>
      {caseDoc && <Pill tone={caseDoc.stage === "VERIFIED" ? "ok" : "muted"}>{stageLabels[caseDoc.stage] ?? "Review case"}</Pill>}
      <button className="quiet" onClick={onDemo}>Demo controls</button>
    </div>
  </header>;
}
