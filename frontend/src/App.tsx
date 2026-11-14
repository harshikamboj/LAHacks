import { useState } from "react";
import { api } from "./lib/api";
import { usePoll } from "./lib/usePoll";
import { CaseHeader } from "./components/CaseHeader";
import { SourceCards } from "./components/SourceCards";
import { AgentPanel } from "./components/AgentPanel";
import { FailureLab } from "./components/FailureLab";
import { MarketContext } from "./components/MarketContext";
import { ProofPanel } from "./components/ProofPanel";

export default function App() {
  const session = usePoll(api.session, 30000);
  const [token, setToken] = useState("");
  const [loginError, setLoginError] = useState("");
  const [loggingIn, setLoggingIn] = useState(false);
  const signedIn = !!session.data;
  const health = usePoll(api.health);
  const sources = usePoll(api.sources);
  // The case document lives in Atlas; don't poll for it until the API reports Atlas connected.
  const atlasReady = !!health.data?.atlas.ok;
  const caseDoc = usePoll(api.caseDoc, 1000, atlasReady);
  const proof = usePoll(api.proof);
  const demo = usePoll(api.demoState);

  const caseError = !atlasReady
    ? "case engine not connected"
    : caseDoc.error
      ? caseDoc.error.status === 404 ? "case not found" : caseDoc.error.message
      : null;

  const refreshAll = () => {
    sources.refresh(); proof.refresh(); demo.refresh();
    if (atlasReady) caseDoc.refresh();
  };

  return (
    <div className="app">
      <CaseHeader health={health.data} sources={sources.data} caseDoc={caseDoc.data} caseError={caseError} />
      {health.error && <div className="banner bad" role="alert">{health.error.message}</div>}
      <form className="reviewer-bar" onSubmit={async (e) => {
        e.preventDefault(); setLoggingIn(true); setLoginError("");
        try { await api.login(token); setToken(""); session.refresh(); }
        catch (err) { setLoginError(err instanceof Error ? err.message : "Sign-in failed"); }
        finally { setLoggingIn(false); }
      }}>
        <span>Local demo reviewer · {session.data?.reviewerId ?? "sign in to operate"}</span>
        {!signedIn && <>
          <label>Reviewer token <input type="password" value={token} autoComplete="current-password"
            onChange={e => setToken(e.target.value)} required /></label>
          <button disabled={loggingIn}>Sign in</button>
        </>}
        {loginError && <span className="bad-text" role="alert">{loginError}</span>}
      </form>
      <main>
        <MarketContext caseDoc={caseDoc.data} />
        <SourceCards sources={sources.data} error={sources.error?.message ?? null} />
        <AgentPanel caseDoc={caseDoc.data} authenticated={signedIn} onChange={refreshAll} />
        <div className="grid-2 bottom">
          <ProofPanel proof={proof.data} error={proof.error?.message ?? null} caseDoc={caseDoc.data} />
          <FailureLab authenticated={signedIn} workerOnline={!!health.data?.worker.online} state={demo.data} error={demo.error?.message ?? null} onChange={refreshAll} />
        </div>
      </main>
      <footer className="foot">
        SEC market observations are historical public context. All trades, accounts, amendments and receipts are simulated. Accepted for processing does not mean final settlement.
      </footer>
    </div>
  );
}
