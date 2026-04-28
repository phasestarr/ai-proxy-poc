import "./login-page.css";

type LoginPageProps = {
  authStatus: "booting" | "anonymous";
  authError: string | null;
  isGuestLoginPending: boolean;
  isLoginVisible: boolean;
  isMicrosoftLoginPending: boolean;
  onGuestLogin: () => Promise<void> | void;
  onMicrosoftLogin: () => void;
};

export default function LoginPage({
  authStatus,
  authError,
  isGuestLoginPending,
  isLoginVisible,
  isMicrosoftLoginPending,
  onGuestLogin,
  onMicrosoftLogin,
}: LoginPageProps) {
  return (
    <main className="auth-shell">
      <section className="auth-stage">
        {authStatus === "booting" || !isLoginVisible ? (
          <section className="auth-status">
            <p className="auth-status-label">Auth</p>
            <p className="auth-status-text">
              {authStatus === "booting" ? "Checking your current session..." : "Preparing sign-in options..."}
            </p>
          </section>
        ) : (
          <section className="login-card">
            <p className="login-eyebrow">Login</p>
            <h1 className="login-title">Authentication</h1>
            <p className="login-copy">
              Microsoft sign-in stays backend-owned.<br/>
              Front only keeps local HttpOnly session cookie.
            </p>

            <div className="login-actions">
              <button
                className="login-button login-button--microsoft"
                disabled={isMicrosoftLoginPending}
                onClick={onMicrosoftLogin}
                type="button"
              >
                {isMicrosoftLoginPending ? "Redirecting to Microsoft..." : "Continue with Microsoft"}
              </button>
              <button
                className="login-button login-button--guest"
                disabled={isGuestLoginPending || isMicrosoftLoginPending}
                onClick={() => void onGuestLogin()}
                type="button"
              >
                {isGuestLoginPending ? "Opening guest session..." : "Guest Login"}
              </button>
            </div>

            <p className="login-hint">ver. 0.2.5-pre-Cypher</p>
            {authError ? <p className="login-error">{authError}</p> : null}
          </section>
        )}
      </section>
    </main>
  );
}
