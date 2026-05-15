import { useAuthSession } from "./auth/useAuthSession";
import SessionConflictDialog from "./components/auth/SessionConflictDialog";
import ChatPage from "./pages/ChatPage";
import LoginPage from "./pages/LoginPage";

export default function App() {
  const auth = useAuthSession();

  const appContent = !auth.session ? (
    <LoginPage
      authError={auth.authError}
      authStatus={auth.authStatus === "anonymous" ? "anonymous" : "booting"}
      isGuestLoginPending={auth.isGuestLoginPending}
      isLoginVisible={auth.isLoginVisible}
      isMicrosoftLoginPending={auth.isMicrosoftLoginPending}
      onGuestLogin={auth.handleGuestLogin}
      onMicrosoftLogin={auth.handleMicrosoftLogin}
    />
  ) : (
    <ChatPage
      onLogout={auth.handleLogout}
      onSessionConflict={auth.handleSessionConflict}
      onSessionExpired={auth.handleSessionExpired}
      session={auth.session}
    />
  );

  return (
    <>
      {appContent}
      {auth.sessionConflict ? (
        <SessionConflictDialog
          conflict={auth.sessionConflict}
          isPending={auth.isSessionConflictPending}
          onLeave={auth.handleSessionConflictLeave}
          onResolve={auth.handleSessionConflictResolve}
        />
      ) : null}
    </>
  );
}
