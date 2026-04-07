type AuthType = "guest" | "microsoft";

const AUTH_ERROR_MESSAGES: Record<string, string> = {
  microsoft_login_cancelled: "Microsoft sign-in was cancelled.",
  microsoft_login_expired: "Microsoft sign-in expired. Try again.",
  microsoft_login_failed: "Microsoft sign-in failed. Try again.",
  microsoft_login_invalid_state: "Microsoft sign-in could not be verified. Try again.",
  microsoft_login_unavailable: "Microsoft sign-in is not configured.",
};

type SessionApiPayload = {
  user_id: string;
  auth_type: AuthType;
  display_name: string;
  email: string | null;
  capabilities: string[];
  persistent: boolean;
  idle_expires_at: string;
  absolute_expires_at: string;
};

type AuthSessionEnvelope = {
  authenticated: true;
  session: SessionApiPayload;
};

type ErrorPayload = {
  detail?: string;
  reason?: string;
};

export type AuthSession = {
  userId: string;
  authType: AuthType;
  displayName: string;
  email: string | null;
  capabilities: string[];
  persistent: boolean;
  idleExpiresAt: string;
  absoluteExpiresAt: string;
};

export class AuthenticationRequiredError extends Error {
  constructor(message = "authentication required") {
    super(message);
    this.name = "AuthenticationRequiredError";
  }
}

export async function fetchCurrentSession(): Promise<AuthSession | null> {
  const response = await fetch("/api/v1/auth/me", {
    credentials: "same-origin",
  });

  if (response.status === 401) {
    return null;
  }

  const payload = (await readJson(response)) as AuthSessionEnvelope | ErrorPayload | null;
  if (!response.ok) {
    const detail = payload && "detail" in payload && payload.detail ? payload.detail : "request failed";
    throw new Error(detail);
  }

  if (!payload || !("authenticated" in payload) || !payload.authenticated) {
    throw new Error("invalid auth payload");
  }

  return mapSession(payload.session);
}

export async function loginAsGuest(): Promise<AuthSession> {
  const response = await fetch("/api/v1/auth/login/guest", {
    method: "POST",
    credentials: "same-origin",
  });

  const payload = (await readJson(response)) as AuthSessionEnvelope | ErrorPayload | null;
  if (!response.ok) {
    const detail = payload && "detail" in payload && payload.detail ? payload.detail : "guest login failed";
    throw new Error(detail);
  }

  if (!payload || !("authenticated" in payload) || !payload.authenticated) {
    throw new Error("invalid auth payload");
  }

  return mapSession(payload.session);
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

export function beginMicrosoftLogin(returnTo = getCurrentReturnTo()): void {
  const url = new URL("/api/v1/auth/login/microsoft", window.location.origin);
  url.searchParams.set("return_to", normalizeReturnTo(returnTo));
  window.location.assign(url.toString());
}

export function consumeAuthErrorFromLocation(): string | null {
  const url = new URL(window.location.href);
  const authErrorCode = url.searchParams.get("auth_error");
  if (!authErrorCode) {
    return null;
  }

  url.searchParams.delete("auth_error");
  const nextLocation = `${url.pathname}${url.search}${url.hash}`;
  window.history.replaceState({}, document.title, nextLocation);

  return AUTH_ERROR_MESSAGES[authErrorCode] ?? "Sign-in failed. Try again.";
}

function mapSession(payload: SessionApiPayload): AuthSession {
  return {
    userId: payload.user_id,
    authType: payload.auth_type,
    displayName: payload.display_name,
    email: payload.email,
    capabilities: payload.capabilities,
    persistent: payload.persistent,
    idleExpiresAt: payload.idle_expires_at,
    absoluteExpiresAt: payload.absolute_expires_at,
  };
}

async function readJson(response: Response): Promise<unknown | null> {
  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    return null;
  }

  return response.json();
}

function getCurrentReturnTo(): string {
  return normalizeReturnTo(`${window.location.pathname}${window.location.search}${window.location.hash}`);
}

function normalizeReturnTo(returnTo: string): string {
  if (!returnTo.startsWith("/") || returnTo.startsWith("//")) {
    return "/";
  }

  return returnTo;
}
