import type { Sources } from "../lib/api";
import { Card, Empty, Field, Pill, time } from "./ui";

function Meta({ request, fetchedAt }: { request: string | null; fetchedAt: string }) {
  return <p className="meta mono">{request ?? "no request"} · read {time(fetchedAt)}</p>;
}

export function SourceCards({ sources, error }: { sources: Sources | null; error: string | null }) {
  if (!sources) {
    return <div className="grid-3"><Card title="Sources of truth"><Empty>{error ?? "Reading the three systems…"}</Empty></Card></div>;
  }
  const { broker, directory, custodian } = sources;
  const t = broker.data;
  const i = custodian.data;
  const baseline = directory.baselineAccountStatus;
  return (
    <div className="grid-3">
      <Card title="Broker" aside={<Pill tone="muted">simulated</Pill>}>
        <p className="role">Owns the executed trade</p>
        {t ? (
          <dl>
            <Field label="Trade">{t.tradeId}</Field>
            <Field label="Order">{t.side} {t.quantity} {t.security} @ {t.currency} {t.price}</Field>
            <Field label="Status"><Pill tone={t.status === "EXECUTED" ? "ok" : "warn"}>{t.status}</Pill></Field>
          </dl>
        ) : <Empty>{broker.error}</Empty>}
        <Meta request={broker.request} fetchedAt={broker.fetchedAt} />
      </Card>

      <Card title="Account directory" aside={<Pill tone="muted">simulated</Pill>}>
        <p className="role">Owns the current receiving account</p>
        {directory.ok ? (
          <>
            <dl>
              <Field label="Contract">v{directory.contract?.version ?? "?"} · {directory.contract?.accountPath}</Field>
              {baseline && (
                <Field label={baseline.accountId}>
                  <Pill tone={baseline.status === "RETIRED" ? "bad" : "ok"}>{baseline.status}</Pill>
                </Field>
              )}
            </dl>
            <details>
              <summary>Live response (shape changes with the contract)</summary>
              <pre>{JSON.stringify(directory.data, null, 2)}</pre>
            </details>
          </>
        ) : <Empty>{directory.error}</Empty>}
        <Meta request={directory.request} fetchedAt={directory.fetchedAt} />
      </Card>

      <Card title="Custodian" aside={<Pill tone="muted">simulated</Pill>}>
        <p className="role">Owns the instruction and the receipt</p>
        {i ? (
          <dl>
            <Field label="Instruction">{i.instructionId} · rev {i.revision}</Field>
            <Field label="Account">{i.safekeepingAccount}</Field>
            <Field label="Status"><Pill tone={i.status === "ACCEPTED" ? "ok" : "bad"}>{i.status}</Pill></Field>
            {i.status === "REJECTED" && <Field label="Reason" mono={false}>{i.rejectionReason}</Field>}
            {i.latestOperationId && <Field label="Operation">{i.latestOperationId}</Field>}
          </dl>
        ) : <Empty>{custodian.error}</Empty>}
        <Meta request={custodian.request} fetchedAt={custodian.fetchedAt} />
      </Card>
    </div>
  );
}
