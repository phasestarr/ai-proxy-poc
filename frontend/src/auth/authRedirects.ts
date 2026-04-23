const AUTH_ERROR_MESSAGES: Record<string, string> = {
  microsoft_login_cancelled: "Microsoft sign-in was cancelled.",
  microsoft_login_expired: "Microsoft sign-in expired. Try again.",
  microsoft_login_failed: "Microsoft sign-in failed. Try again.",
  microsoft_login_invalid_state: "Microsoft sign-in could not be verified. Try again.",
  microsoft_login_unavailable: "Microsoft sign-in is not configured.",
  session_limit_reached: "This account has too many active sessions.",
};

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

function getCurrentReturnTo(): string {
  return normalizeReturnTo(`${window.location.pathname}${window.location.search}${window.location.hash}`);
}

function normalizeReturnTo(returnTo: string): string {
  if (!returnTo.startsWith("/") || returnTo.startsWith("//")) {
    return "/";
  }

  return returnTo;
}

