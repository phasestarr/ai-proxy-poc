import type { AuthSession } from "../../../auth/authTypes";
import { getSessionLabel } from "../formatters";

type ChatToolbarProps = {
  session: AuthSession;
  onLogout: () => Promise<void> | void;
};

export default function ChatToolbar({ session, onLogout }: ChatToolbarProps) {
  const sessionLabel = getSessionLabel(session);

  return (
    <header className="chat-toolbar" role="group" aria-label="Session controls">
      <div className="chat-toolbar-copy">
        <p className="chat-toolbar-label">{session.authType === "guest" ? "Guest session" : "Microsoft session"}</p>
        <p className="chat-toolbar-name">{sessionLabel}</p>
      </div>
      <button
        aria-label={`Log out ${sessionLabel}`}
        className="chat-toolbar-button"
        onClick={() => void onLogout()}
        type="button"
      >
        Log Out
      </button>
    </header>
  );
}

