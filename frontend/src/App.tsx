import { useEffect, useRef, useState } from "react";
import { api } from "./lib/api";
import { usePoll } from "./lib/usePoll";
import { currentStep, friendlyError, stageLabels, workflowSteps } from "./lib/presentation";
import { CaseHeader } from "./components/CaseHeader";
import { SourceCards } from "./components/SourceCards";
import { AgentPanel } from "./components/AgentPanel";
import { FailureLab } from "./components/FailureLab";
import { MarketContext } from "./components/MarketContext";

export default function App() {
  const [selected, setSelected] = useState<string | null>(null);
  const cases = usePoll(api.cases);
  const followupReady = !!cases.data?.some(c => c.scenarioKind === "account_correction" && c.stage === "VERIFIED" && c.learning?.status === "STORED");
  if (selected) return <CaseWorkspace key={selected} caseId={selected} onBack={() => setSelected(null)} />;
  return <><header className="product-header"><div className="brand"><span className="brand-mark">T↗</span><strong>TradeOps</strong><span>Settlement operations</span></div><span className="connection connected">Demonstration work queue</span></header>
    <main className="queue-page"><span className="eyebrow">Settlement operations</span><h1>Work through the exceptions.</h1><p className="lead">Open an instruction, reconcile its records, and confirm the outcome. Verified corrections become experience for similar cases.</p>
      {cases.error && <p role="alert" className="notice warning">The work queue is temporarily unavailable.</p>}
      {!cases.data && !cases.error && <p>Loading saved cases…</p>}
      <div className="case-queue">{cases.data?.map((c, i) => <button key={c.caseId} className="queue-item" disabled={c.scenarioKind === "similar_exception" && !followupReady} onClick={() => setSelected(c.caseId)}><span className="queue-order">{String(i + 1).padStart(2,"0")}</span><span><strong>{c.title ?? c.caseId}</strong><small>{c.caseId} · Portfolio {c.portfolioId}</small>{c.learning?.status === "STORED" && <small className="learned-label">Verified experience saved for future cases</small>}</span><span className="queue-state">{c.scenarioKind === "similar_exception" && !followupReady ? "Available after verified experience is saved" : `${stageLabels[c.stage] ?? c.stage} →`}</span></button>)}</div>
      <p className="muted">Suggested sequence: resolve the first case, wait for its experience to save, then open the similar exception. The other cases demonstrate no-change and specialist-review outcomes.</p>
      <footer>TradeOps implements the ProofStep control layer. All trades and account actions are simulated; each correction requires its own approval.</footer>
    </main></>;
}

function CaseWorkspace({caseId, onBack}: {caseId: string; onBack: () => void}) {
  const session = usePoll(api.session, 30000);
  const [token, setToken] = useState("");
  const [loginError, setLoginError] = useState("");
  const [loggingIn, setLoggingIn] = useState(false);
  const [demoOpen, setDemoOpen] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);
  const signedIn = !!session.data && !session.error;
  const health = usePoll(api.health);
  const sources = usePoll(() => api.sources(caseId));
  const atlasReady = !!health.data?.atlas.ok;
  const caseDoc = usePoll(() => api.caseDoc(caseId), 1000, atlasReady);
  const proof = usePoll(() => api.proof(caseId));
  const demo = usePoll(() => api.demoState(caseId));
  const step = currentStep(caseDoc.data?.stage, !!caseDoc.data?.operation);
  const completed = caseDoc.data?.stage === "VERIFIED";
  useEffect(() => {
    if (demoOpen) dialog.current?.showModal();
    else dialog.current?.close();
  }, [demoOpen]);
  const refreshAll = () => {
    sources.refresh(); proof.refresh(); demo.refresh(); health.refresh();
    if (atlasReady) caseDoc.refresh();
  };
  return <>
    <CaseHeader health={health.data} caseDoc={caseDoc.data} onDemo={() => setDemoOpen(true)} />
    <div className="app-shell">
      <aside className="journey">
        <span className="eyebrow">Settlement operations</span><h2>Resolve an exception</h2><p>One instruction. A verified outcome.</p>
        <ol className="journey-steps">{workflowSteps.map((item, i) => <li key={item.title} className={completed || i < step ? "done" : i === step ? "current" : ""} aria-current={!completed && i === step ? "step" : undefined}><span className="step-number">{completed || i < step ? "✓" : String(i + 1).padStart(2, "0")}</span><div><strong>{item.title}</strong><small>{item.description}</small></div></li>)}</ol>
        <div className="case-reference"><span className="eyebrow">Assigned case</span><strong>{caseDoc.data?.caseId ?? caseId}</strong><span>{sources.data?.broker.data?.security ?? "—"} · {sources.data?.broker.data?.portfolioId ?? "—"}</span><small>Simulated settlement instruction</small></div>
      </aside>
      <main id="main-content">
        <div className="breadcrumb"><button className="back-link" onClick={onBack}>← Work queue</button> <span>/</span> {caseDoc.data?.caseId ?? caseId}</div>
        <div className="reviewer-bar">{signedIn ? <span><i /> Reviewer: {session.data?.reviewerId}</span> : <form onSubmit={async e => {
          e.preventDefault(); setLoggingIn(true); setLoginError("");
          try { await api.login(token); setToken(""); session.refresh(); }
          catch (error) { setLoginError(friendlyError(error)); }
          finally { setLoggingIn(false); }
        }}><label>Reviewer access code <input type="password" value={token} autoComplete="current-password" onChange={e => setToken(e.target.value)} required /></label><button disabled={loggingIn}>{loggingIn ? "Signing in…" : "Sign in"}</button></form>}{loginError && <span role="alert" className="bad-text">{loginError}</span>}</div>
        {(health.error || caseDoc.error || (!atlasReady && health.data)) && <p className="notice warning" role="alert">Live case records are unavailable. Previously loaded information may be out of date. Reconnect before proceeding.</p>}
        {sources.data?.broker.data && <p className="trade-context">{sources.data.broker.data.side === "BUY" ? "Buy" : sources.data.broker.data.side} {sources.data.broker.data.quantity} {sources.data.broker.data.security}<span>Portfolio {sources.data.broker.data.portfolioId}</span><span>Settlement {sources.data.broker.data.settlementDate}</span></p>}
        <AgentPanel caseDoc={caseDoc.data} authenticated={signedIn && atlasReady && !caseDoc.error && !health.error} onChange={refreshAll} health={health.data} demo={demo.data} proof={proof.data} proofError={proof.error?.message ?? null} sources={sources.data} onBack={onBack} />
        <MarketContext caseDoc={caseDoc.data} />
        <SourceCards sources={sources.data} error={sources.error?.message ?? null} />
        <footer>TradeOps · Protected by the ProofStep control layer. Trades, accounts and corrections are simulated. SEC observations are historical public context.</footer>
      </main>
    </div>
    <dialog ref={dialog} className="demo-dialog" aria-labelledby="demo-dialog-title" onCancel={() => setDemoOpen(false)} onClose={() => setDemoOpen(false)}>
      <header className="drawer-header"><div><span className="eyebrow">Presenter workspace</span><h2 id="demo-dialog-title">Demo controls</h2></div><button autoFocus onClick={() => setDemoOpen(false)} aria-label="Close demo controls">Close ×</button></header>
      <p className="muted">Introduce a system change or interruption, then return to the case to show recovery.</p>
      <FailureLab caseId={caseId} authenticated={signedIn} workerOnline={!!health.data?.worker.online} state={demo.data} error={demo.error?.message ?? null} onChange={refreshAll} />
      <details className="technical"><summary>Service diagnostics</summary><pre>{JSON.stringify(health.data, null, 2)}</pre></details>
    </dialog>
  </>;
}
