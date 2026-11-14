import type { CaseDoc } from "../lib/api";

export function MarketContext({ caseDoc }: { caseDoc: CaseDoc | null }) {
  const context = caseDoc?.marketContext;
  const observation = context?.observation;
  if (!context) return null;
  return <aside className="market-note" aria-label="Historical market context">
    <span className="eyebrow">Public market context · SEC</span>
    {observation ? <p><strong>{observation.symbol || observation.cusip}</strong> had <strong>{observation.outstanding_fail_quantity.toLocaleString()} market-wide outstanding failed shares</strong> reported on {observation.settlement_date.slice(0, 10)}. Prior close: {observation.prior_close_price ?? "not reported"}.</p> : <p>No public observation was reported for this trade’s security and settlement date.</p>}
    <small>Matched by security identifier and settlement date. This historical aggregate is separate from the simulated trade and stays unchanged by its correction.</small>
    {observation && <details className="technical"><summary>View dataset reference</summary><p>{observation.description} · {observation.source_archive} · {context.observationId}</p></details>}
  </aside>;
}
