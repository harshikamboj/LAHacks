// Typed client for the TradeOps API. Every value the UI shows comes through here — nothing is hardcoded.

export const CASE_ID = "SI-2041";

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message);
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  let resp: Response;
  try {
    resp = await fetch(`/api${path}`, {
      method,
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "API_UNREACHABLE", "Can't reach the TradeOps API on :8000");
  }
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    const err = (data as { error?: { code?: string; message?: string }; detail?: string }).error;
    throw new ApiError(resp.status, err?.code ?? `HTTP_${resp.status}`, err?.message ?? resp.statusText);
  }
  return data as T;
}

// ---------- types ----------

export interface Health {
  api: string;
  atlas: { ok: boolean; status: string; db: string; error: string | null };
  simulators: Record<string, { ok: boolean; url: string; error?: string }>;
  worker: { online: boolean; status?: string; workerId?: string; ageSeconds?: number };
  memory: { vectorSearch: string; reason: string | null };
  demoMode: boolean;
}

export interface SourceCard<T> {
  ok: boolean;
  request: string | null;
  fetchedAt: string;
  data?: T;
  error?: string;
}

export interface Trade {
  tradeId: string; portfolioId: string; side: string; security: string;
  quantity: number; price: string; currency: string; status: string; executedAt: string;
}

export interface Instruction {
  instructionId: string; tradeId: string; portfolioId: string; security: string; quantity: number;
  revision: number; safekeepingAccount: string; status: string;
  rejectionReason: string | null; rejectionNote: string | null; latestOperationId: string | null; updatedAt: string;
}

export interface Contract { version: number; accountPath: string; changedAt: string }
export interface AccountStatus { accountId: string; portfolioId: string; status: string; authorized: boolean; retiredOn: string | null }

export interface Sources {
  caseId: string;
  broker: SourceCard<Trade>;
  directory: SourceCard<Record<string, unknown>> & { contract?: Contract; baselineAccountStatus?: AccountStatus };
  custodian: SourceCard<Instruction>;
}

export interface Proof {
  instructionId: string; currentRevision: number; currentAccount: string; status: string;
  receiptCount: number; patchRequestCount: number;
  receipts: { receiptId: string; operationId: string; resultRevision: number; committedAt: string }[];
  revisions: { revision: number; account: string; status: string; operationId: string | null; createdAt: string }[];
  patchRequests: { idempotencyKey: string | null; outcome: string; receivedAt: string }[];
}

export interface DemoState {
  faults: { lostResponse: boolean; operationsUnavailable: boolean };
  directoryContractVersion: number;
  crashWorkerOnUnknown: boolean | null;
}

export interface CaseEvent { at: string; type: string; stage?: string; actor?: string; detail?: string }

export interface CaseDoc {
  caseId: string; stage: string; version: number;
  investigation?: {
    steps?: { n: number; tool: string; request: string; ok: boolean; summary: string; guidedBy?: string | null }[];
    precedents?: { query: string; status: string; incidentId?: string; score?: number; reason?: string }[];
    diagnosis?: string;
  };
  proposal?: Record<string, unknown> & { expectedRevision: number; oldAccount: string; newAccount: string; policyVersion: string };
  proposalHash?: string;
  approval?: { reviewerId: string; approvedAt: string };
  operation?: { operationId: string; attemptCount: number };
  checkpoint?: { savedByWorkerId?: string; savedAt?: string };
  verification?: { receiptId?: string; resumedByWorkerId?: string; verifiedAt?: string };
  manualReview?: { code: string; detail: string };
  events?: CaseEvent[];
}

// ---------- calls ----------

export const api = {
  health: () => request<Health>("GET", "/health"),
  sources: () => request<Sources>("GET", `/cases/${CASE_ID}/sources`),
  caseDoc: () => request<CaseDoc>("GET", `/cases/${CASE_ID}`),
  proof: () => request<Proof>("GET", "/demo/custodian-proof"),
  demoState: () => request<DemoState>("GET", "/demo/state"),
  setFaults: (f: Partial<{ lostResponse: boolean; operationsUnavailable: boolean; crashWorkerOnUnknown: boolean }>) =>
    request("POST", "/demo/faults", f),
  setDirectoryVersion: (version: 1 | 2 | 3) => request("POST", "/demo/directory-version", { version }),
  reset: () => request("POST", "/demo/reset", { confirm: "RESET" }),
};
