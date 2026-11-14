import { useState } from "react";
import { api, type DemoState } from "../lib/api";
import { friendlyError } from "../lib/presentation";

export function FailureLab({ state, error, onChange, authenticated, workerOnline, caseId }: {
  caseId: string; authenticated: boolean; workerOnline: boolean; state: DemoState | null; error: string | null; onChange: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  async function act(label: string, fn: () => Promise<unknown>) {
    setBusy(true); setMessage(null);
    try { await fn(); setMessage(label); }
    catch (error) { setMessage(friendlyError(error)); }
    finally { setBusy(false); onChange(); }
  }
  if (!state) return <p>{error ? "Demo services are unavailable." : "Loading demo controls…"}</p>;
  const disabled = busy || !authenticated;
  return <div className="lab">
    <section className="lab-section"><span className="eyebrow">1 / Change a supporting system</span><h3>Account record format</h3><p>Switch the directory while reconciliation is paused to demonstrate adaptation.</p>
      <div className="segmented">{([1, 2, 3] as const).map(v => <button key={v} disabled={disabled} aria-pressed={state.directoryContractVersion === v} className={state.directoryContractVersion === v ? "on" : ""} onClick={() => act("Directory record format updated.", () => api.setDirectoryVersion(v))}>{v === 1 ? "Original format" : v === 2 ? "Updated format" : "Unsupported format"}</button>)}</div>
      <label className="toggle"><input type="checkbox" checked={state.pauseDirectoryRead} disabled={disabled} onChange={e => act("Account-check pause updated.", () => api.setFaults({pauseDirectoryRead: e.target.checked}, caseId))} /><span>Pause before checking account records<small>Gives the presenter time to change the directory.</small></span></label>
      {state.directoryPaused && <p className="notice">The case is paused. Choose the updated format, close this panel, then select Continue reconciliation.</p>}
    </section>
    <section className="lab-section"><span className="eyebrow">2 / Demonstrate recovery</span><h3>Interrupt an approved correction</h3><p>Enable both controls before applying the approved correction.</p>
      <label className="toggle"><input type="checkbox" checked={state.faults.lostResponse} disabled={disabled} onChange={e => act("Confirmation delay updated.", () => api.setFaults({lostResponse: e.target.checked}, caseId))} /><span>Delay the custodian’s confirmation<small>The correction is recorded, but its reply arrives too late. One use.</small></span></label>
      <label className="toggle"><input type="checkbox" checked={!!state.crashWorkerOnUnknown} disabled={disabled} onChange={e => act("Processing interruption updated.", () => api.setFaults({crashWorkerOnUnknown: e.target.checked}, caseId))} /><span>Interrupt processing after submission<small>Actually exits the worker when the reply is uncertain.</small></span></label>
      <p className="hint">After the interruption, run <code>./scripts/worker.sh</code> in the project terminal. The case resumes from its saved correction.</p>
    </section>
    <details className="lab-section"><summary>Additional failure scenarios</summary>
      <label className="toggle"><input type="checkbox" checked={state.faults.operationsUnavailable} disabled={disabled} onChange={e => act("Confirmation-service availability updated.", () => api.setFaults({operationsUnavailable: e.target.checked}, caseId))} /><span>Make confirmation records unavailable<small>Demonstrates waiting and specialist referral instead of a blind retry.</small></span></label>
      <label className="toggle"><input type="checkbox" checked={state.crashBeforeSend} disabled={disabled} onChange={e => act("Pre-submission interruption updated.", () => api.setFaults({crashBeforeSend: e.target.checked}, caseId))} /><span>Interrupt before submission<small>Alternative scenario: exit after saving the correction, before sending it.</small></span></label>
    </details>
    <section className="lab-section"><h3>Start another rehearsal</h3><p>Archives all queue cases and resets the simulated instructions. Market data and past experience are preserved.</p><button className="danger" disabled={disabled || workerOnline} onClick={() => {
      if (window.confirm("Archive this rehearsal and reset the simulated instruction? Market data and past experience will be preserved.")) act("A fresh case is ready. Restart the reconciliation service.", api.reset);
    }}>Start fresh demo</button><p className="hint">{workerOnline ? "Stop the worker first with ./scripts/stop-worker.sh, or use ./scripts/reset.sh from the project terminal." : "Restart the worker after resetting with ./scripts/worker.sh."}</p></section>
    {!authenticated && <p className="notice warning">Sign in as the demo reviewer to change these controls.</p>}
    {message && <p className="lab-msg" role="status">{message}</p>}
  </div>;
}
