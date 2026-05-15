import { readJson } from "../api/http";
import type { AuthIssuePayload, SessionConflictInfo } from "./authTypes";

export class AuthenticationRequiredError extends Error {
  constructor(message = "authentication required") {
    super(message);
    this.name = "AuthenticationRequiredError";
  }
}

export class SessionConflictError extends Error {
  conflict: SessionConflictInfo;

  constructor(conflict: SessionConflictInfo) {
    super(conflict.detail);
    this.name = "SessionConflictError";
    this.conflict = conflict;
  }
}

export async function readSessionConflict(response: Response): Promise<SessionConflictError> {
  const payload = (await readJson(response)) as AuthIssuePayload | null;
  return new SessionConflictError({
    reason: payload?.reason ?? "session_conflict",
    detail: payload?.detail ?? "This session needs attention.",
    redirectTo: payload?.redirect_to ?? "/",
    canEvictOldest: payload?.can_evict_oldest ?? false,
    authType: payload?.auth_type ?? null,
    sessionLimit: payload?.session_limit ?? null,
  });
}

