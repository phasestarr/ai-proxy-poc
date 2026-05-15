import type { SessionConflictInfo } from "../../auth/authTypes";

type SessionConflictDialogProps = {
  conflict: SessionConflictInfo;
  isPending: boolean;
  onLeave: () => Promise<void> | void;
  onResolve: () => Promise<void> | void;
};

export default function SessionConflictDialog({
  conflict,
  isPending,
  onLeave,
  onResolve,
}: SessionConflictDialogProps) {
  return (
    <div className="session-conflict-overlay" role="dialog" aria-modal="true" aria-labelledby="session-conflict-title">
      <section className="session-conflict-card">
        <p className="session-conflict-eyebrow">Session Conflict</p>
        <h2 className="session-conflict-title" id="session-conflict-title">
          This browser session was replaced.
        </h2>
        <p className="session-conflict-copy">{conflict.detail}</p>
        <p className="session-conflict-meta">
          {conflict.authType ? `Auth type: ${conflict.authType}` : "Auth type unavailable"}
          {conflict.sessionLimit ? ` · Limit: ${conflict.sessionLimit}` : ""}
        </p>
        <div className="session-conflict-actions">
          <button className="session-conflict-button session-conflict-button--secondary" onClick={() => void onLeave()} type="button">
            Go to Home
          </button>
          <button
            className="session-conflict-button session-conflict-button--primary"
            disabled={!conflict.canEvictOldest || isPending}
            onClick={() => void onResolve()}
            type="button"
          >
            {isPending ? "Recovering..." : "Evict Oldest Session"}
          </button>
        </div>
      </section>
    </div>
  );
}

