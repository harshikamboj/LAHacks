import { ApiError } from "./api";

export const workflowSteps = [
  { title: "Review exception", description: "Understand the rejected instruction" },
  { title: "Reconcile records", description: "Find and validate the receiving account" },
  { title: "Authorize correction", description: "Review and approve the exact change" },
  { title: "Confirm completion", description: "Apply once and verify the outcome" },
];
export function currentStep(stage?: string, hasOperation = false): number {
  if (!stage || stage === "NEW") return 0;
  if (stage === "MANUAL_REVIEW" && hasOperation) return 3;
  if (stage === "INVESTIGATING" || stage === "MANUAL_REVIEW" || stage === "NO_ACTION") return 1;
  if (stage === "AWAITING_APPROVAL" || stage === "APPROVED" || stage === "DENIED") return 2;
  return 3;
}
export const stageLabels: Record<string, string> = {
  NEW: "Action needed", INVESTIGATING: "Reconciling records", AWAITING_APPROVAL: "Awaiting your review",
  APPROVED: "Approved · ready to apply", AWAITING_VERIFICATION: "Confirming outcome", VERIFIED: "Correction confirmed",
  DENIED: "Correction declined", MANUAL_REVIEW: "Specialist review needed", NO_ACTION: "No correction needed",
};
export const toolLabels: Record<string, string> = {
  get_custodian_instruction: "Reviewed the rejected settlement instruction",
  get_broker_trade: "Checked the executed trade against the instruction",
  get_directory_contract: "Validated the directory’s updated record format",
  get_directory_account: "Confirmed the current receiving-account record",
  get_account_status: "Checked account ownership and eligibility",
};
export const eventLabels: Record<string, string> = {
  EXPERIENCE_RETRY_REQUESTED: "Reviewer requested another experience-publication attempt", EXPERIENCE_LOOKUP_PENDING: "Waiting for verified past experience", EXPERIENCE_CHECKED: "Checked for learned procedures", EXPERIENCE_REUSED: "A completed case guided the next check", EXPERIENCE_SAVED: "Verified experience saved for future cases", EXPERIENCE_PENDING: "Experience publication pending",
  CASE_OPENED: "Exception opened", INVESTIGATION_REQUESTED: "Reconciliation started", TOOL_CALLED: "Supporting record checked",
  MARKET_CONTEXT_READ: "Historical market context matched", DIRECTORY_READ_PAUSED: "Waiting at the account-directory check",
  PRECEDENT_RETRIEVED: "Relevant experience retrieved", RETRIEVAL_PENDING: "Past experience temporarily unavailable",
  PROPOSAL_CREATED: "Correction ready for review", APPROVED: "Reviewer approved the correction", DENIED: "Reviewer declined the correction",
  APPROVAL_INVALIDATED: "Records changed · fresh approval required", EXECUTION_REQUESTED: "Application requested",
  INTENT_PERSISTED: "Approved correction saved for safe recovery", PATCH_SENT: "Correction submitted to the custodian",
  ACK_RECEIVED: "Custodian reply received · verification next", OUTCOME_UNKNOWN: "Reply unavailable · checking the outcome",
  RESUMED_FROM_CHECKPOINT: "Work resumed from the saved correction", RETRY_SAME_KEY: "Confirmed absent · resubmitting the original correction",
  VERIFICATION_DEFERRED: "Waiting for the custodian’s confirmation service", VERIFIED: "Correction independently confirmed",
  NO_ACTION: "Instruction already accepted · no change needed", MANUAL_REVIEW: "Case referred for specialist review",
  FAULT_CONFIGURED: "Demo scenario adjusted",
};
export function friendlyError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 401) return "Sign in with your reviewer access code to continue.";
    if (error.code === "WORKER_RUNNING") return "Stop the reconciliation service before starting a fresh demo.";
    if (error.status === 409) return "This case has changed. Wait for the latest record, then review your action again.";
    if (error.status === 403) return "Your reviewer access does not permit this action.";
    if (error.status === 0 || error.status >= 500) return "A supporting service is unavailable. Your last saved case is preserved; try again when it reconnects.";
  }
  return "We couldn’t complete this action. Refresh the case and try again.";
}
