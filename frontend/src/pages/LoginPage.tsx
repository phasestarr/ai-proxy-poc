import "./login-page.css";

type LoginPageProps = {
  authStatus: "booting" | "anonymous";
  authError: string | null;
  isGuestLoginPending: boolean;
  isLoginVisible: boolean;
  onGuestLogin: () => Promise<void> | void;
};

export default function LoginPage({
  authStatus,
  authError,
  isGuestLoginPending,
  isLoginVisible,
  onGuestLogin,
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
            <h1 className="login-title">Choose your access path.</h1>
            <p className="login-copy">
              Microsoft SSO will attach here next. Guest stays available below for debugging and alternate auth flows.
            </p>

            <div className="login-actions">
              <button className="login-button login-button--microsoft" disabled type="button">
                Microsoft MSAL
              </button>
              <button
                className="login-button login-button--guest"
                disabled={isGuestLoginPending}
                onClick={() => void onGuestLogin()}
                type="button"
              >
                {isGuestLoginPending ? "Opening guest session..." : "Guest Login"}
              </button>
            </div>

            <p className="login-hint">No client token storage. The browser only carries an HttpOnly session cookie.</p>
            {authError ? <p className="login-error">{authError}</p> : null}
          </section>
        )}
      </section>
    </main>
  );
}
