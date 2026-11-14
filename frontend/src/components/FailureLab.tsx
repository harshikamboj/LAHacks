import { useState } from "react";
import { api, ApiError, type DemoState } from "../lib/api";
import { Card, Empty, Pill } from "./ui";

export function FailureLab({ state, error, onChange }: {
  state: DemoState | null; error: string | null; onChange: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function act(label: string, fn: () => Promise<unknown>) {
    setBusy(true);
    setMessage(null);
    try {
      await fn();
      setMessage(label);
    } catch (e) {
      setMessage(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e));
    } finally {
      setBusy(false);
      onChange();
    }
  }

  function reset() {
    if (window.confirm("Reset all synthetic demo data in the three simulators?")) {
      act("Demo data reset", api.reset);
    }
  }

  return (
    <Card title="Failure lab" aside={<Pill tone="warn">demo mode only</Pill>}>
      {!state ? <Empty>{error ?? "Loading demo controls…"}</Empty> : (
        <div className="lab">
          <label className="toggle">
            <input type="checkbox" checked={state.faults.lostResponse} disabled={busy}
              onChange={(e) => act("Lost-response fault updated", () => api.setFaults({ lostResponse: e.target.checked }))} />
            Lose the custodian's next reply <span className="hint">(commits, then drops the response once)</span>
          </label>
          <label className="toggle">
            <input type="checkbox" checked={state.faults.operationsUnavailable} disabled={busy}
              onChange={(e) => act("Operation lookup fault updated", () => api.setFaults({ operationsUnavailable: e.target.checked }))} />
            Custodian operation lookup unavailable <span className="hint">(503, not absence)</span>
          </label>
          <label className="toggle">
            <input type="checkbox" checked={!!state.crashWorkerOnUnknown} disabled={busy || state.crashWorkerOnUnknown === null}
              onChange={(e) => act("Crash flag updated", () => api.setFaults({ crashWorkerOnUnknown: e.target.checked }))} />
            Crash the worker on an unknown outcome
            <span className="hint">{state.crashWorkerOnUnknown === null ? "(available once the worker exists)" : "(real process exit)"}</span>
          </label>
          <div className="segmented" role="group" aria-label="Directory contract version">
            <span>Directory contract</span>
            {([1, 2, 3] as const).map((v) => (
              <button key={v} disabled={busy} aria-pressed={state.directoryContractVersion === v}
                className={state.directoryContractVersion === v ? "on" : ""}
                onClick={() => act(`Directory switched to v${v}`, () => api.setDirectoryVersion(v))}>
                v{v}{v === 3 ? " (unknown)" : ""}
              </button>
            ))}
          </div>
          <button className="danger" disabled={busy} onClick={reset}>Reset demo</button>
          {message && <p className="lab-msg" role="status">{message}</p>}
        </div>
      )}
    </Card>
  );
}
