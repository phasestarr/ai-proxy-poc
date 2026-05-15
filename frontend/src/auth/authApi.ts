import { readJson } from "../api/http";
import { AuthenticationRequiredError, readSessionConflict } from "./authErrors";
import { mapAuthSession } from "./sessionMapper";
import type { AuthIssuePayload, AuthSession, AuthSessionEnvelope, AuthType } from "./authTypes";

export async function fetchCurrentSession(): Promise<AuthSession | null> {
  const response = await fetch("/api/v1/auth/me", {
    credentials: "same-origin",
  });

  if (response.status === 409) {
    throw await readSessionConflict(response);
  }

  if (response.status === 401) {
    return null;
  }

  const payload = (await readJson(response)) as AuthSessionEnvelope | AuthIssuePayload | null;
  if (!response.ok) {
    const detail = payload && "detail" in payload && payload.detail ? payload.detail : "request failed";
    throw new Error(detail);
  }

  if (!payload || !("authenticated" in payload) || !payload.authenticated) {
    throw new Error("invalid auth payload");
  }

  return mapAuthSession(payload.session);
}

export async function loginAsGuest(): Promise<AuthSession> {
  const response = await fetch("/api/v1/auth/login/guest", {
    method: "POST",
    credentials: "same-origin",
  });

  if (response.status === 409) {
    throw await readSessionConflict(response);
  }

  const payload = (await readJson(response)) as AuthSessionEnvelope | AuthIssuePayload | null;
  if (!response.ok) {
    const detail = payload && "detail" in payload && payload.detail ? payload.detail : "guest login failed";
    throw new Error(detail);
  }

  if (!payload || !("authenticated" in payload) || !payload.authenticated) {
    throw new Error("invalid auth payload");
  }

  return mapAuthSession(payload.session);
}

export async function logoutCurrentSession(): Promise<void> {
  const response = await fetch("/api/v1/auth/logout", {
    method: "POST",
    credentials: "same-origin",
  });

  if (!response.ok && response.status !== 401) {
    throw new Error("logout failed");
  }
}

export async function resolveSessionConflict(options: { authType?: AuthType | null } = {}): Promise<AuthSession> {
  const response = await fetch("/api/v1/auth/session-conflicts/resolve", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      resolution: "evict_oldest",
      auth_type: options.authType ?? null,
    }),
  });

  if (response.status === 409) {
    throw await readSessionConflict(response);
  }

  if (response.status === 401) {
    const payload = (await readJson(response)) as AuthIssuePayload | null;
    throw new AuthenticationRequiredError(payload?.detail || "authentication required");
  }

  const payload = (await readJson(response)) as AuthSessionEnvelope | AuthIssuePayload | null;
  if (!response.ok) {
    const detail = payload && "detail" in payload && payload.detail ? payload.detail : "session recovery failed";
    throw new Error(detail);
  }

  if (!payload || !("authenticated" in payload) || !payload.authenticated) {
    throw new Error("invalid auth payload");
  }

  return mapAuthSession(payload.session);
}

