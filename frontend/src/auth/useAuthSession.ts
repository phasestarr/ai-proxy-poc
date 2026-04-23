import { useEffect, useState } from "react";

import { fetchCurrentSession, loginAsGuest, logoutCurrentSession, resolveSessionConflict } from "./authApi";
import { beginMicrosoftLogin, consumeAuthErrorFromLocation } from "./authRedirects";
import { AuthenticationRequiredError, SessionConflictError } from "./authErrors";
import type { AuthSession, AuthStatus, SessionConflictInfo } from "./authTypes";

const LOGIN_DELAY_MS = 500;

export function useAuthSession() {
  const [authStatus, setAuthStatus] = useState<AuthStatus>("booting");
  const [session, setSession] = useState<AuthSession | null>(null);
  const [authError, setAuthError] = useState<string | null>(null);
  const [sessionConflict, setSessionConflict] = useState<SessionConflictInfo | null>(null);
  const [isLoginVisible, setIsLoginVisible] = useState(false);
  const [isGuestLoginPending, setIsGuestLoginPending] = useState(false);
  const [isMicrosoftLoginPending, setIsMicrosoftLoginPending] = useState(false);
  const [isSessionConflictPending, setIsSessionConflictPending] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const locationAuthError = consumeAuthErrorFromLocation();
    if (locationAuthError) {
      setAuthError(locationAuthError);
    }

    const bootstrap = async () => {
      try {
        const currentSession = await fetchCurrentSession();
        if (cancelled) {
          return;
        }

        if (!currentSession) {
          setSession(null);
          setAuthStatus("anonymous");
          return;
        }

        setSession(currentSession);
        setAuthStatus(getStatusFromSession(currentSession));
        setSessionConflict(null);
      } catch (error) {
        if (cancelled) {
          return;
        }

        if (error instanceof SessionConflictError) {
          applySessionConflict(error.conflict);
          return;
        }

        const detail = error instanceof Error ? error.message : "Failed to resolve your current session.";
        setAuthError(detail);
        setSession(null);
        setAuthStatus("anonymous");
      }
    };

    void bootstrap();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    setIsLoginVisible(false);

    if (authStatus !== "anonymous") {
      return;
    }

    const timeoutId = window.setTimeout(() => {
      setIsLoginVisible(true);
    }, LOGIN_DELAY_MS);

    return () => {
      window.clearTimeout(timeoutId);
    };
  }, [authStatus]);

  const applySessionConflict = (conflict: SessionConflictInfo) => {
    setSession(null);
    setAuthError(null);
    setAuthStatus("anonymous");
    setSessionConflict(conflict);
  };

  const handleGuestLogin = async () => {
    if (isGuestLoginPending) {
      return;
    }

    setAuthError(null);
    setSessionConflict(null);
    setIsGuestLoginPending(true);

    try {
      const nextSession = await loginAsGuest();
      setSession(nextSession);
      setAuthStatus(getStatusFromSession(nextSession));
      setSessionConflict(null);
    } catch (error) {
      if (error instanceof SessionConflictError) {
        applySessionConflict(error.conflict);
        return;
      }

      const detail = error instanceof Error ? error.message : "Guest login failed.";
      setAuthError(detail);
      setSession(null);
      setAuthStatus("anonymous");
    } finally {
      setIsGuestLoginPending(false);
    }
  };

  const handleMicrosoftLogin = () => {
    if (isMicrosoftLoginPending) {
      return;
    }

    setAuthError(null);
    setSessionConflict(null);
    setIsMicrosoftLoginPending(true);
    beginMicrosoftLogin();
  };

  const handleLogout = async () => {
    try {
      await logoutCurrentSession();
    } finally {
      setSession(null);
      setAuthError(null);
      setSessionConflict(null);
      setAuthStatus("anonymous");
    }
  };

  const handleSessionExpired = () => {
    setSession(null);
    setSessionConflict(null);
    setAuthError("Your session expired. Sign in again to continue.");
    setAuthStatus("anonymous");
  };

  const handleSessionConflict = (conflict: SessionConflictInfo) => {
    applySessionConflict(conflict);
  };

  const handleSessionConflictResolve = async () => {
    if (!sessionConflict || !sessionConflict.canEvictOldest || isSessionConflictPending) {
      return;
    }

    setAuthError(null);
    setIsSessionConflictPending(true);

    try {
      const nextSession = await resolveSessionConflict({ authType: sessionConflict.authType });
      setSession(nextSession);
      setAuthStatus(getStatusFromSession(nextSession));
      setSessionConflict(null);
    } catch (error) {
      if (error instanceof SessionConflictError) {
        setSessionConflict(error.conflict);
        return;
      }

      if (error instanceof AuthenticationRequiredError) {
        setSession(null);
        setAuthStatus("anonymous");
        setSessionConflict(null);
        setAuthError(error.message);
        return;
      }

      const detail = error instanceof Error ? error.message : "Session recovery failed.";
      setAuthError(detail);
    } finally {
      setIsSessionConflictPending(false);
    }
  };

  const handleSessionConflictLeave = async () => {
    const redirectTo = sessionConflict?.redirectTo ?? "/";
    try {
      await logoutCurrentSession();
    } finally {
      setSession(null);
      setAuthStatus("anonymous");
      setSessionConflict(null);
    }
    window.location.assign(redirectTo);
  };

  return {
    authStatus,
    session,
    authError,
    sessionConflict,
    isLoginVisible,
    isGuestLoginPending,
    isMicrosoftLoginPending,
    isSessionConflictPending,
    handleGuestLogin,
    handleMicrosoftLogin,
    handleLogout,
    handleSessionExpired,
    handleSessionConflict,
    handleSessionConflictResolve,
    handleSessionConflictLeave,
  };
}

function getStatusFromSession(session: AuthSession): AuthStatus {
  return session.authType === "microsoft" ? "microsoft" : "guest";
}

