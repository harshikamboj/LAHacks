import type { CaseDoc } from "../lib/api";
import { Card, Field, Pill } from "./ui";

export function MarketContext({caseDoc}: {caseDoc: CaseDoc | null}) {
  const context = caseDoc?.marketContext;
  const observation = context?.observation;
  return <Card title="Market context · SEC observation" className="market-context"
    aside={<Pill tone="info">historical public data</Pill>}>
    {observation ? <>
      <div className="market-grid">
        <dl><Field label="Security">{observation.symbol || "Symbol unavailable"} · {observation.cusip}</Field>
          <Field label="Observed date">{observation.settlement_date.slice(0,10)}</Field></dl>
        <dl><Field label="Outstanding">{observation.outstanding_fail_quantity.toLocaleString()} market-wide shares</Field>
          <Field label="Prior close">{observation.prior_close_price ?? "Not reported"}</Field></dl>
      </div>
      <p className="meta">{observation.description} · {observation.source_archive} · CUSIP/date join: {context?.observationId}</p>
    </> : <p>{context?.status === "NONE" ? "No reported observation for the verified broker CUSIP/date. Investigation continues." :
      "Start investigation to attach the SEC observation using the broker’s verified CUSIP and settlement date."}</p>}
    <p className="scope-note">The dataset reports aggregate outstanding delivery failures across market participants.
      The 100-share trade, retired account and amendment below are a separate fictional scenario.
      Correcting this simulated instruction does not change the published market observation.</p>
  </Card>;
}
