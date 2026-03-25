import { useEffect, useState } from "react";

import ChatPage from "./pages/ChatPage";
import LoginPage from "./pages/LoginPage";
import { fetchCurrentSession, loginAsGuest, logoutCurrentSession, type AuthSession } from "./services/authService";

type AuthStatus = "booting" | "anonymous" | "guest" | "microsoft";

const LOGIN_DELAY_MS = 500;

export default function App() {
  const [authStatus, setAuthStatus] = useState<AuthStatus>("booting");
  const [session, setSession] = useState<AuthSession | null>(null);
  const [authError, setAuthError] = useState<string | null>(null);
  const [isLoginVisible, setIsLoginVisible] = useState(false);
  const [isGuestLoginPending, setIsGuestLoginPending] = useState(false);

  useEffect(() => {
    let cancelled = false;

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
      } catch (error) {
        if (cancelled) {
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

  const handleGuestLogin = async () => {
    if (isGuestLoginPending) {
      return;
    }

    setAuthError(null);
    setIsGuestLoginPending(true);

    try {
      const nextSession = await loginAsGuest();
      setSession(nextSession);
      setAuthStatus(getStatusFromSession(nextSession));
    } catch (error) {
      const detail = error instanceof Error ? error.message : "Guest login failed.";
      setAuthError(detail);
      setSession(null);
      setAuthStatus("anonymous");
    } finally {
      setIsGuestLoginPending(false);
    }
  };

  const handleLogout = async () => {
    try {
      await logoutCurrentSession();
    } finally {
      setSession(null);
      setAuthError(null);
      setAuthStatus("anonymous");
    }
  };

  const handleSessionExpired = () => {
    setSession(null);
    setAuthError("Your session expired. Sign in again to continue.");
    setAuthStatus("anonymous");
  };

  if (!session) {
    return (
      <LoginPage
        authError={authError}
        authStatus={authStatus === "anonymous" ? "anonymous" : "booting"}
        isGuestLoginPending={isGuestLoginPending}
        isLoginVisible={isLoginVisible}
        onGuestLogin={handleGuestLogin}
      />
    );
  }

  return <ChatPage onLogout={handleLogout} onSessionExpired={handleSessionExpired} session={session} />;
}

function getStatusFromSession(session: AuthSession): AuthStatus {
  return session.authType === "microsoft" ? "microsoft" : "guest";
}
