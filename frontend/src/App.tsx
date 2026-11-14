import { api } from "./lib/api";
import { usePoll } from "./lib/usePoll";
import { CaseHeader } from "./components/CaseHeader";
import { SourceCards } from "./components/SourceCards";
import { AgentPanel } from "./components/AgentPanel";
import { FailureLab } from "./components/FailureLab";
import { ProofPanel } from "./components/ProofPanel";

export default function App() {
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
      <main>
        <SourceCards sources={sources.data} error={sources.error?.message ?? null} />
        <AgentPanel caseDoc={caseDoc.data} />
        <div className="grid-2 bottom">
          <ProofPanel proof={proof.data} error={proof.error?.message ?? null} caseDoc={caseDoc.data} />
          <FailureLab state={demo.data} error={demo.error?.message ?? null} onChange={refreshAll} />
        </div>
      </main>
      <footer className="foot">
        Synthetic data only. Broker, directory and custodian are simulators with their own databases. No real trades, accounts or settlement.
      </footer>
    </div>
  );
}
